"""
Legacy Finnish CV review used by `POST /ai/review`: prompts, JSON parsing,
heuristic fallback and the response format the existing frontends expect.
"""
import json
import re

from aibot.review.extract import normalize_whitespace

# Completion-style prompt for the local and Puter providers.
REVIEW_PROMPT_TEMPLATE = (
    "Ansioluettelo:\n{resume_text}\n\n"
    "Arvostelu: Tämä on"
)

# Structured prompt for Gemini — deep analysis with explicit criteria.
VERTEX_REVIEW_PROMPT_TEMPLATE = (
    "Olet kokenut rekrytoija ja ansioluettelon arvioija. Analysoi seuraava ansioluettelo perusteellisesti "
    "ja arvioi jokainen alla oleva kriteeri erikseen.\n\n"
    "Arviointikriteerit:\n"
    "1. Yhteystiedot — nimi, sähköposti, puhelin, LinkedIn/portfolio\n"
    "2. Ammatillinen tiivistelmä tai profiili — onko selkeä ja houkutteleva\n"
    "3. Työkokemus — työnimikkeet, työnantajat, päivämäärät, vastuut ja saavutukset\n"
    "4. Koulutus — tutkinnot, oppilaitokset, valmistumisvuodet\n"
    "5. Taidot ja osaaminen — tekniset taidot, kielet, sertifikaatit\n"
    "6. Saavutukset — mitattavat tulokset, luvut, prosentit\n"
    "7. Rakenne ja luettavuus — selkeä jäsentely, johdonmukaisuus\n"
    "8. Pituus ja kattavuus — riittävä yksityiskohtaisuus suhteessa kokemukseen\n"
    "9. ATS-yhteensopivuus — selkeät otsikot, ei taulukoita tai erikoismerkkejä\n"
    "10. Kokonaisvaikutelma — erottuuko CV edukseen\n\n"
    "Ansioluettelo:\n{resume_text}\n\n"
    "Palauta vastauksesi AINOASTAAN seuraavassa JSON-muodossa ilman muuta tekstiä tai markdown-koodimerkkejä:\n"
    '{{\n'
    '  "stars": <kokonaisluku 0-5>,\n'
    '  "rating_text": "<Erinomainen|Erittäin hyvä|Hyvä|Tyydyttävä|Heikko|Huono>",\n'
    '  "summary": "<kattava yhteenveto suomeksi, 2-4 lausetta>",\n'
    '  "strengths": ["<konkreettinen vahvuus 1>", "<konkreettinen vahvuus 2>", "<konkreettinen vahvuus 3>"],\n'
    '  "weaknesses": ["<kehityskohde 1>", "<kehityskohde 2>", "<kehityskohde 3>"]\n'
    '}}'
)


def map_rating_text(stars: int) -> str:
    """Map numeric score to rubric text."""
    if stars >= 5:
        return "Erinomainen"
    if stars >= 4:
        return "Erittäin hyvä"
    if stars >= 3:
        return "Hyvä"
    if stars >= 2:
        return "Tyydyttävä"
    if stars >= 1:
        return "Heikko"
    return "Huono"


def extract_json_from_text(text: str) -> dict | None:
    """Pull the first JSON object found in the model output."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def beautify_provider_output(text: str) -> str:
    """
    Clean and beautify provider raw output for display.
    - Removes markdown formatting
    - Converts escape sequences to readable text
    - Ensures proper capitalization
    - Removes special characters
    """
    if not text:
        return text
    
    # Remove markdown bold/italic markers
    cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)
    
    # Remove markdown headers
    cleaned = re.sub(r'^#+\s+', '', cleaned, flags=re.MULTILINE)
    
    # Convert newlines to proper spacing (double newlines become paragraph breaks)
    cleaned = cleaned.replace('\\n\\n', '\n\n')
    cleaned = cleaned.replace('\\n', ' ')
    cleaned = cleaned.replace('\n\n', '\n\n')
    cleaned = cleaned.replace('\n', ' ')
    
    # Remove multiple spaces
    cleaned = re.sub(r' +', ' ', cleaned)
    
    # Remove leading/trailing whitespace
    cleaned = cleaned.strip()
    
    # Ensure first letter is uppercase
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    
    return cleaned


def _format_default_provider_output(
    model_output: str,
    summary: str,
    strengths: list[str],
    weaknesses: list[str],
    rating_text: str,
    stars: int
) -> str:
    """Return a readable detailed output for the local model provider."""
    cleaned = normalize_whitespace(model_output)

    # Keep a meaningful cleaned version when the model output is usable.
    looks_usable = len(cleaned) >= 80 and not cleaned.startswith("{")
    if looks_usable:
        return cleaned[:1200]

    # Fallback to a deterministic, detailed text when generation is noisy.
    strengths_text = "; ".join(strengths) if strengths else "Ei havaittuja vahvuuksia"
    weaknesses_text = "; ".join(weaknesses) if weaknesses else "Ei havaittuja kehityskohteita"

    return (
        f"Arvioinnin yhteenveto: {summary} "
        f"Kokonaisarvosana: {rating_text} ({stars}/5). "
        f"Vahvuudet: {strengths_text}. "
        f"Kehityskohteet: {weaknesses_text}."
    )


def analyze_resume_heuristics(parsed_text: str) -> dict:
    """Simple heuristic analysis when model doesn't produce structured output."""
    text_lower = parsed_text.lower()
    words = parsed_text.split()
    word_count = len(words)
    
    # Start with low baseline - poor CV by default
    score = 2
    strengths = []
    weaknesses = []
    
    # Critical minimums
    if word_count < 20:
        weaknesses.append("Liian lyhyt ansioluettelo (alle 20 sanaa)")
        score = 1
    elif word_count < 50:
        weaknesses.append("Hyvin lyhyt ansioluettelo")
        score = 3
    else:
        score = 5  # Acceptable length
        strengths.append(f"Riittävä pituus ({word_count} sanaa)")
    
    # Required sections — Finnish and English keywords
    has_experience = any(word in text_lower for word in [
        'kokemus', 'työkokemus', 'työ', 'työnantaja',
        'experience', 'employment', 'work history', 'position', 'employer'
    ])
    has_education = any(word in text_lower for word in [
        'koulutus', 'opiskelu', 'tutkinto', 'yliopisto', 'koulu', 'ammattikoulu',
        'education', 'degree', 'university', 'bachelor', 'master', 'diploma', 'college'
    ])
    has_skills = any(word in text_lower for word in [
        'osaaminen', 'taito', 'kieli', 'sertifikaatti',
        'skills', 'technologies', 'languages', 'certifications', 'competencies'
    ])
    has_contact = (
        '@' in parsed_text
        or any(word in text_lower for word in ['puhelin', 'email', 'phone', 'linkedin', 'github', 'portfolio'])
    )
    has_summary = any(word in text_lower for word in [
        'tiivistelmä', 'profiili', 'yhteenveto',
        'summary', 'profile', 'objective', 'about'
    ])
    has_achievements = any(word in text_lower for word in [
        'saavutus', 'tulos', 'parannus', 'kasvu',
        'achievement', 'accomplishment', 'improved', 'increased', 'reduced', 'led', '%'
    ])
    has_dates = bool(re.search(r'\b(19|20)\d{2}\b', parsed_text))
    has_projects = any(word in text_lower for word in [
        'projekti', 'vastuualue', 'johtaminen', 'kehittäminen',
        'project', 'responsibility', 'managed', 'developed', 'led'
    ])

    if has_experience:
        score += 1
        strengths.append("Sisältää työkokemuksen")
    else:
        weaknesses.append("Työkokemus puuttuu tai epäselvä")

    if has_education:
        score += 1
        strengths.append("Sisältää koulutustiedot")
    else:
        weaknesses.append("Koulutustiedot puuttuvat")

    if has_skills:
        score += 1
        strengths.append("Sisältää osaamistiedot")
    else:
        weaknesses.append("Osaamistiedot puuttuvat")

    if has_contact:
        score += 1
        strengths.append("Yhteystiedot löytyvät")
    else:
        weaknesses.append("Yhteystiedot puuttuvat")

    if has_summary:
        score += 1
        strengths.append("Sisältää ammatillisen tiivistelmän")
    else:
        weaknesses.append("Ammatillinen tiivistelmä puuttuu")

    if has_achievements:
        score += 1
        strengths.append("Sisältää mitattavia saavutuksia")
    else:
        weaknesses.append("Mitattavat saavutukset puuttuvat")

    if has_dates:
        score += 1
        strengths.append("Päivämäärät merkitty selkeästi")
    else:
        weaknesses.append("Päivämäärät puuttuvat tai epäselvät")

    if has_projects:
        score += 1
        strengths.append("Sisältää konkreettisia projekteja/vastuita")

    # Length bonuses
    if word_count > 200:
        score += 1
        strengths.append("Kattava sisältö")

    if word_count > 400:
        score += 1
        strengths.append("Erittäin yksityiskohtainen")
        
    # Normalize to 0-5 scale
    score = max(0, min(5, int(round(score / 2))))
    
    # Default strengths/weaknesses if empty
    if not strengths:
        strengths = ["Ansioluettelo on luettavissa"]
    if not weaknesses:
        weaknesses = ["Ei merkittäviä puutteita"]
    
    return {
        "stars": score,
        "rating_text": map_rating_text(score),
        "summary": "",
        "strengths": strengths,
        "weaknesses": weaknesses
    }


def format_summary_by_rating(rating_text: str, base_summary: str) -> str:
    """Add generic rating-aware text to the summary."""
    rating_map = {
        "Erinomainen": (
            "Yleisarvio: Erinomainen. Ansioluettelo vaikuttaa hyvin jäsennellyltä ja kattavalta, "
            "ja sisältö antaa selkeän kokonaiskuvan osaamisesta ja kokemuksesta. "
            "Rakenne tukee luettavuutta ja keskeiset tiedot erottuvat hyvin."
        ),
        "Erittäin hyvä": (
            "Yleisarvio: Erittäin hyvä. Ansioluettelo on selkeä ja monipuolinen, "
            "ja tärkeimmät tiedot ovat helposti löydettävissä. "
            "Kokonaisuus on vahva ja antaa hyvän kuvan taustasta."
        ),
        "Hyvä": (
            "Yleisarvio: Hyvä. Ansioluettelo kattaa perusasiat ja tarjoaa yleiskuvan taustasta, "
            "mutta kokonaisuutta voi vielä tarkentaa ja selkeyttää. "
            "Tietojen esitystapaa ja sanavalintoja kehittämällä vaikutelma vahvistuu."
        ),
        "Tyydyttävä": (
            "Yleisarvio: Tyydyttävä. Ansioluettelo sisältää joitakin keskeisiä tietoja, "
            "mutta rakenne ja sisältö kaipaavat selkeytystä. "
            "Täydennä puuttuvat tiedot ja jäsennä sisältö selkeämmin."
        ),
        "Heikko": (
            "Yleisarvio: Heikko. Ansioluettelo on suppea tai epäselvä, "
            "eikä kokonaiskuvaa osaamisesta ja kokemuksesta synny. "
            "Lisää keskeiset osiot ja kuvaa sisältöä tarkemmin."
        ),
        "Huono": (
            "Yleisarvio: Huono. Ansioluettelosta puuttuu keskeisiä osioita tai rakenne on epäselvä, "
            "mikä vaikeuttaa kokonaiskuvan muodostamista. "
            "Sisältöä ja selkeyttä lisäämällä arvio paranee merkittävästi."
        ),
    }
    rating_note = rating_map.get(
        rating_text,
        "Yleisarvio: Ei määritetty. Ansioluettelo on analysoitu, mutta yleisarviota ei voitu muodostaa."
    )
    return f"{base_summary} {rating_note}"


def build_review_response(parsed_text: str, model_output: str, provider: str = "default") -> dict:
    """Build response from model output with heuristic fallback."""
    # Try to extract JSON first
    parsed = extract_json_from_text(model_output) or {}

    # If we got valid JSON with stars, use it
    if "stars" in parsed and parsed.get("stars") is not None:
        summary = parsed.get("summary") or model_output.strip()[:200]
        strengths = parsed.get("strengths") if isinstance(parsed.get("strengths"), list) else []
        weaknesses = parsed.get("weaknesses") if isinstance(parsed.get("weaknesses"), list) else []

        raw_stars = parsed.get("stars")
        try:
            stars = int(float(raw_stars))
        except (TypeError, ValueError):
            stars = 5
        stars = max(0, min(5, stars))

        rating_text = parsed.get("rating_text")
        if rating_text not in {"Erinomainen", "Erittäin hyvä", "Hyvä", "Tyydyttävä", "Heikko", "Huono"}:
            rating_text = map_rating_text(stars)
    else:
        # Fallback to heuristic analysis
        heuristic = analyze_resume_heuristics(parsed_text)
        stars = heuristic["stars"]
        rating_text = heuristic["rating_text"]
        summary = f"{heuristic['summary']}"
        strengths = heuristic["strengths"]
        weaknesses = heuristic["weaknesses"]

    summary = format_summary_by_rating(rating_text, summary)

    provider_raw_output = model_output
    if provider == "default":
        provider_raw_output = _format_default_provider_output(
            model_output=model_output,
            summary=summary,
            strengths=strengths,
            weaknesses=weaknesses,
            rating_text=rating_text,
            stars=stars
        )

    return {
        "rating_text": rating_text,
        "stars": stars,
        "summary": summary,
        "provider_raw_output": provider_raw_output,
        "strengths": strengths,
        "weaknesses": weaknesses
    }
