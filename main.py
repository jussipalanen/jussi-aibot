from fastapi import FastAPI
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

app = FastAPI(title="Jussi AI Bot", version="0.1.0", description="A simple AI bot built with FastAPI and PyTorch.")

# --------------------------
# Load small model
# --------------------------
model_name = "EleutherAI/gpt-neo-125M"  # small, fast model for testing
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)
generator = pipeline("text-generation", model=model, tokenizer=tokenizer)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello World from Python and FastAPI!"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/ai/ask/{question}")
async def ai_ask(question: str) -> dict[str, str]:
    prompt = f"You are a helpful and funny AI assistant. Answer this question: {question}"
    response = generator(prompt, max_new_tokens=50, temperature=0.7)
    answer = response[0]['generated_text']
    return {"question": question, "answer": answer}