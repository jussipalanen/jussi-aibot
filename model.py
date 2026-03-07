"""
Model loader for the Finnish resume review service.
"""
from transformers import AutoModelForCausalLM, AutoTokenizer

# --------------------------
# Load TurkuNLP GPT-3 Finnish model (causal LM for Finnish text generation)
# --------------------------
MODEL_NAME = "TurkuNLP/gpt3-finnish-small"

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)

# Ensure padding token is set for causal LM generation
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# Move to CPU
device = "cpu"
model = model.to(device)
