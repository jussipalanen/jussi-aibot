"""
Service functions for resume text extraction and analysis.
"""
from fastapi import HTTPException, status
from functools import lru_cache
import io
import json
import os
import re
import subprocess
import tempfile

import pdfplumber
from docx import Document

def _local_model_disabled() -> bool:
    value = os.getenv("DISABLE_LOCAL_MODEL", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def _get_local_model():
    if _local_model_disabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local model is disabled. Use provider=puter_ai instead."
        )

    # Lazy import to avoid Hugging Face download at startup
    from model import model, tokenizer, device
    return model, tokenizer, device


def detect_language(text: str) -> str:
    """
    Language detection - currently only Finnish is supported.
    Returns 'fi' for Finnish.
    """
    # Only Finnish language is supported
    return "fi"


def generate_review_default(prompt: str) -> str:
    """Generate review text with the local Finnish model."""
    model, tokenizer, device = _get_local_model()
    encoded = tokenizer(prompt, return_tensors="pt").to(device)
    input_ids = encoded.input_ids

    outputs = model.generate(
        input_ids,
        max_new_tokens=300,
        temperature=0.8,
        top_p=0.92,
        do_sample=True,
        repetition_penalty=1.1,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id
    )

    generated_ids = outputs[0]
    new_tokens = generated_ids[input_ids.shape[-1]:]
    if new_tokens.numel() == 0:
        new_tokens = generated_ids

    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def _extract_puter_text(response: object) -> str:
    """Extract text from Puter response shape safely."""
    if isinstance(response, str):
        return response.strip()

    if isinstance(response, dict):
        # Puter SDK common shape:
        # {"success": true, "result": {"message": {"content": "..."}}}
        result = response.get("result")
        if isinstance(result, dict):
            message = result.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()

        # Surface explicit provider error payloads when present.
        if response.get("success") is False:
            error_msg = response.get("error") or response.get("message")
            if isinstance(error_msg, str) and error_msg.strip():
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Puter AI request failed: {error_msg.strip()}"
                )

        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content.strip()
                text = first.get("text")
                if isinstance(text, str):
                    return text.strip()

        message = response.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
        content = response.get("content")
        if isinstance(content, str):
            return content.strip()

    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        first = choices[0]
        message = getattr(first, "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if isinstance(content, str):
                return content.strip()
        text = getattr(first, "text", None)
        if isinstance(text, str):
            return text.strip()

    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content.strip()

    # Debug: log the response structure
    import json
    try:
        response_debug = json.dumps(response, default=str, indent=2)
    except:
        response_debug = str(response)
    
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Puter AI returned an unreadable response. Response structure: {response_debug[:500]}"
    )


def generate_review_puter_ai(prompt: str) -> str:
    """Generate review text with Puter AI SDK."""
    api_key = os.getenv("PUTER_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Puter AI is not configured. Missing PUTER_API_KEY."
        )

    model_name = os.getenv("PUTER_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    driver = os.getenv("PUTER_DRIVER", "openai-completion").strip() or "openai-completion"

    try:
        from puter import ChatCompletion
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Puter AI SDK is not installed."
        ) from exc

    try:
        response = ChatCompletion.create(
            messages=[{"role": "user", "content": prompt}],
            model=model_name,
            driver=driver,
            api_key=api_key
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Puter AI request failed: {exc}"
        ) from exc

    return _extract_puter_text(response)


def generate_review_vertex_ai(prompt: str) -> str:
    """Generate review text with Google Vertex AI (Gemini)."""
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vertex AI SDK is not installed. Run: pip install google-cloud-aiplatform"
        ) from exc

    project = os.getenv("GCP_PROJECT", "").strip()
    location = os.getenv("GCP_LOCATION", "europe-west1").strip() or "europe-west1"
    model_name = os.getenv("VERTEX_MODEL", "gemini-1.5-pro").strip() or "gemini-1.5-pro"

    if not project:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vertex AI is not configured. Missing GCP_PROJECT."
        )

    try:
        vertexai.init(project=project, location=location)
        model = GenerativeModel(model_name)
        response = model.generate_content(prompt)
        return response.text
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Vertex AI request failed: {exc}"
        ) from exc


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
        "provider": provider,
        "rating_text": rating_text,
        "stars": stars,
        "summary": summary,
        "provider_raw_output": provider_raw_output,
        "strengths": strengths,
        "weaknesses": weaknesses
    }
