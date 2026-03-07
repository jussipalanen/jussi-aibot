"""
Service functions for resume text extraction and analysis.
"""
from fastapi import HTTPException, status
import io
import json
import os
import re
import subprocess
import tempfile

import pdfplumber
from docx import Document


def detect_language(text: str) -> str:
    """
    Language detection - currently only Finnish is supported.
    Returns 'fi' for Finnish.
    """
    # Only Finnish language is supported
    return "fi"


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


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for stable prompts and cache keys."""
    return re.sub(r"\s+", " ", text).strip()


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from each PDF page."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract paragraph text from DOCX files."""
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    return "\n".join(paragraphs)


def extract_text_from_doc(file_bytes: bytes) -> str:
    """Use antiword for legacy DOC files."""
    with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp_file:
        tmp_file.write(file_bytes)
        tmp_path = tmp_file.name
    try:
        result = subprocess.run(
            ["antiword", tmp_path],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to extract text from DOC file."
            )
        return result.stdout
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def extract_resume_text(file_bytes: bytes, filename: str) -> str:
    """Route extraction by file extension."""
    _, ext = os.path.splitext(filename.lower())
    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)
    if ext == ".docx":
        return extract_text_from_docx(file_bytes)
    if ext in {".doc", ".docs"}:
        return extract_text_from_doc(file_bytes)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported file type."
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
    
    # Required sections
    has_experience = any(word in text_lower for word in ['kokemus', 'työkokemus', 'työ'])
    has_education = any(word in text_lower for word in ['koulutus', 'opiskelu', 'tutkinto', 'yliopisto', 'koulu'])
    has_skills = any(word in text_lower for word in ['osaaminen', 'taito', 'kieli'])
    has_contact = '@' in parsed_text or 'puhelin' in text_lower or 'email' in text_lower
    
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
    
    # Advanced content scoring
    if any(word in text_lower for word in ['projekti', 'vastuualue', 'johtaminen', 'kehittäminen']):
        score += 1
        strengths.append("Sisältää konkreettisia projekteja/vastuita")
    
    if any(word in text_lower for word in ['saavutus', 'tulos', 'parannus', '%', 'kasvu']):
        score += 1
        strengths.append("Sisältää mitattavia saavutuksia")
    
    # Length bonuses for comprehensive CVs
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


def build_review_response(parsed_text: str, model_output: str) -> dict:
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
        if rating_text not in {"Erinomainen", "Erittäin hyvä", "Hyvä", "Huono"}:
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

    return {
        "rating_text": rating_text,
        "stars": stars,
        "summary": summary,
        "strengths": strengths,
        "weaknesses": weaknesses
    }
