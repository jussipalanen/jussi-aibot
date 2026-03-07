from fastapi import FastAPI, File, UploadFile, HTTPException, status
from transformers import AutoModelForCausalLM, AutoTokenizer
import sys
import platform
import torch
import fastapi
import spacy
from spacy_langdetect import LanguageDetector
from spacy.language import Language
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile

import pdfplumber
from docx import Document

app = FastAPI(title="Jussi AI Bot", version="0.1.0", description="A simple AI bot built with FastAPI and PyTorch.")

# --------------------------
# Load TurkuNLP GPT-3 Finnish model (causal LM for Finnish Q&A)
# --------------------------
model_name = "TurkuNLP/gpt3-finnish-small"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

# Ensure padding token is set for causal LM generation
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# Move to CPU
device = "cpu"
model = model.to(device)

# --------------------------
# Initialize language detector
# --------------------------
@Language.factory("language_detector")
def create_language_detector(nlp, name):
    return LanguageDetector()

try:
    nlp = spacy.load("fi_core_news_sm")
except OSError:
    # If model not found, use blank Finnish model
    nlp = spacy.blank("fi")

if "language_detector" not in nlp.pipe_names:
    nlp.add_pipe("language_detector", last=True)

# Resume review prompt template - simplified for base model
REVIEW_PROMPT_TEMPLATE = (
    "Ansioluettelo:\n{resume_text}\n\n"
    "Arvostelu: Tämä on"
)

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docs", ".docx"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# --------------------------
# Response cache for faster repeat questions
# --------------------------
response_cache = {}
cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}

def detect_language(text: str) -> str:
    """
    Detect language of the input text.
    Returns 'fi' for Finnish.
    """
    doc = nlp(text)
    detected_lang = doc._.language.get("language", "fi")
    
    # Only support Finnish
    if detected_lang == "fi":
        return "fi"
    else:
        return "fi"  # Default to Finnish


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello World from Python and FastAPI!"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/version")
async def version() -> dict[str, str]:
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "fastapi_version": fastapi.__version__,
        "torch_version": torch.__version__,
    }

@app.get("/cache/stats")
async def cache_stats_endpoint() -> dict:
    """Get cache performance statistics"""
    hit_rate = (cache_stats["hits"] / cache_stats["total_requests"] * 100) if cache_stats["total_requests"] > 0 else 0
    return {
        "cache_hits": cache_stats["hits"],
        "cache_misses": cache_stats["misses"],
        "total_requests": cache_stats["total_requests"],
        "hit_rate_percent": round(hit_rate, 2),
        "cached_items": len(response_cache)
    }

@app.post("/cache/clear")
async def clear_cache() -> dict[str, str]:
    """Clear the response cache"""
    response_cache.clear()
    cache_stats["hits"] = 0
    cache_stats["misses"] = 0
    cache_stats["total_requests"] = 0
    return {"status": "ok", "message": "Cache cleared successfully"}

def map_rating_text(stars: int) -> str:
    # Map numeric score to rubric text.
    if stars >= 8:
        return "Erinomainen"
    if stars >= 6:
        return "Erittäin hyvä"
    if stars >= 4:
        return "Hyvä"
    return "Huono"


def extract_json_from_text(text: str) -> dict | None:
    # Pull the first JSON object found in the model output.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def normalize_whitespace(text: str) -> str:
    # Normalize whitespace for stable prompts and cache keys.
    return re.sub(r"\s+", " ", text).strip()


def extract_text_from_pdf(file_bytes: bytes) -> str:
    # Extract text from each PDF page.
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def extract_text_from_docx(file_bytes: bytes) -> str:
    # Extract paragraph text from DOCX files.
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    return "\n".join(paragraphs)


def extract_text_from_doc(file_bytes: bytes) -> str:
    # Use antiword for legacy DOC files.
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
    # Route extraction by file extension.
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
        
    # Cap the score
    score = max(0, min(10, score))
    
    # Default strengths/weaknesses if empty
    if not strengths:
        strengths = ["Ansioluettelo on luettavissa"]
    if not weaknesses:
        weaknesses = ["Ei merkittäviä puutteita"]
    
    return {
        "stars": score,
        "rating_text": map_rating_text(score),
        "summary": f"Ansioluettelo sisältää {word_count} sanaa. Arvioitu automaattisesti käyttäen sisällönanalyysiä.",
        "strengths": strengths,
        "weaknesses": weaknesses
    }


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
        stars = max(0, min(10, stars))

        rating_text = parsed.get("rating_text")
        if rating_text not in {"Erinomainen", "Erittäin hyvä", "Hyvä", "Huono"}:
            rating_text = map_rating_text(stars)
    else:
        # Fallback to heuristic analysis
        heuristic = analyze_resume_heuristics(parsed_text)
        stars = heuristic["stars"]
        rating_text = heuristic["rating_text"]
        summary = f"AI-generoitu arvio: {model_output.strip()[:150]}... | {heuristic['summary']}"
        strengths = heuristic["strengths"]
        weaknesses = heuristic["weaknesses"]

    return {
        "rating_text": rating_text,
        "stars": stars,
        "parsed_text": parsed_text,
        "summary": summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "cached": False
    }


@app.post("/ai/review")
async def ai_review(file: UploadFile = File(...)) -> dict:
    # Validate file input and size limits.
    cache_stats["total_requests"] += 1

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File name is required."
        )

    _, ext = os.path.splitext(file.filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type."
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Max size is 50MB."
        )

    parsed_text = normalize_whitespace(extract_resume_text(file_bytes, file.filename))
    if not parsed_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No text could be extracted from the uploaded file."
        )

    detected_lang = detect_language(parsed_text)
    if detected_lang != "fi":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vain suomenkieliset ansioluettelot ovat tuettuja."
        )

    file_hash = hashlib.md5(file_bytes).hexdigest()
    cache_key = hashlib.md5(f"{file_hash}_{detected_lang}".encode()).hexdigest()

    if cache_key in response_cache:
        cache_stats["hits"] += 1
        cached_response = response_cache[cache_key]
        return {**cached_response, "cached": True}

    cache_stats["misses"] += 1

    prompt = REVIEW_PROMPT_TEMPLATE.format(resume_text=parsed_text)
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
    model_output = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    response = build_review_response(parsed_text, model_output)

    if len(response_cache) < 1000:
        response_cache[cache_key] = {
            **response,
            "cached": False
        }

    return response