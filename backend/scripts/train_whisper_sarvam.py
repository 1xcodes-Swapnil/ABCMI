"""
ABCI-MI Production Model Fine-Tuning Suite.
Supports:
1. Whisper (ASR) Fine-Tuning with PEFT / LoRA on AISHELL-1, AMI, and YODAS2
2. Sarvam-1 (Indic LM) Fine-Tuning for Code-Switched Hinglish/Indic Text Normalization
"""

import argparse
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ModelTrainer")


@dataclass
class DataCollatorSpeechSeq2SeqWithPadding:
    """Data collator for Whisper fine-tuning with dynamic batch padding."""

    processor: Any

    def __call__(self, features: List[Dict[str, Union[List[int], Any]]]) -> Dict[str, Any]:
        import torch

        input_features = [{"input_features": feature["input_features"]} for feature in features]
        batch = self.processor.feature_extractor.pad(input_features, return_tensors="pt")

        label_features = [{"input_ids": feature["labels"]} for feature in features]
        labels_batch = self.processor.tokenizer.pad(label_features, return_tensors="pt")

        # Replace padding with -100 to ignore loss correctly
        labels = labels_batch["input_ids"].masked_fill(labels_batch.attention_mask.ne(1), -100)

        # If bos token is prepended in previous steps, cut it off
        if (labels[:, 0] == self.processor.tokenizer.bos_token_id).all().cpu().item():
            labels = labels[:, 1:]

        batch["labels"] = labels
        return batch


def prepare_whisper_dataset(manifest_jsonl: str, processor: Any, language: str = "zh", max_samples: Optional[int] = None):
    """Loads manifest and prepares acoustic spectrograms and token labels."""
    from datasets import Dataset
    import soundfile as sf
    import librosa
    import numpy as np

    data = []
    with open(manifest_jsonl, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if max_samples and i >= max_samples:
                break
            line_data = json.loads(line.strip())
            data.append(line_data)

    logger.info(f"Loaded {len(data)} items from {manifest_jsonl}")

    def load_audio_features(batch):
        audio_path = batch["audio_path"]
        if not os.path.exists(audio_path):
            # Create synthetic silent audio if sample is a placeholder
            audio = np.zeros(16000 * 2, dtype=np.float32)
            sr = 16000
        else:
            audio, sr = librosa.load(audio_path, sr=16000)

        # Compute log-Mel spectrogram
        batch["input_features"] = processor.feature_extractor(audio, sampling_rate=sr).input_features[0]

        # Encode target text to token IDs
        batch["labels"] = processor.tokenizer(batch["text"]).input_ids
        return batch

    raw_dataset = Dataset.from_list(data)
    processed_dataset = raw_dataset.map(load_audio_features, remove_columns=raw_dataset.column_names)
    return processed_dataset


def train_whisper_lora(
    dataset_jsonl: str,
    output_dir: str = "./models/whisper-finetuned",
    model_id: str = "openai/whisper-large-v3",
    language: str = "zh",
    task: str = "transcribe",
    batch_size: int = 4,
    learning_rate: float = 1e-4,
    num_epochs: int = 3,
    use_lora: bool = True,
    max_samples: Optional[int] = None,
):
    """Fine-tunes Whisper using Hugging Face Transformers & PEFT LoRA."""
    import torch
    from transformers import (
        Seq2SeqTrainer,
        Seq2SeqTrainingArguments,
        WhisperForConditionalGeneration,
        WhisperProcessor,
    )

    logger.info(f"--- Initializing Whisper Fine-Tuning ({model_id}) ---")
    logger.info(f"Language: {language} | Task: {task} | LoRA: {use_lora}")

    processor = WhisperProcessor.from_pretrained(model_id, language=language, task=task)
    model = WhisperForConditionalGeneration.from_pretrained(
        model_id,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        low_cpu_mem_usage=True,
    )

    # Disable cache for gradient checkpointing
    model.config.use_cache = False
    model.generate = torch.inference_mode(torch.no_grad())(model.generate)

    if use_lora:
        try:
            from peft import LoraConfig, get_peft_model
            lora_config = LoraConfig(
                r=32,
                lora_alpha=64,
                target_modules=["q_proj", "v_proj"],
                lora_dropout=0.05,
                bias="none",
            )
            model = get_peft_model(model, lora_config)
            model.print_trainable_parameters()
        except ImportError:
            logger.warning("`peft` not installed. Proceeding with standard fine-tuning.")

    train_dataset = prepare_whisper_dataset(dataset_jsonl, processor, language=language, max_samples=max_samples)
    data_collator = DataCollatorSpeechSeq2SeqWithPadding(processor=processor)

    training_args = Seq2SeqTrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=2,
        learning_rate=learning_rate,
        num_train_epochs=num_epochs,
        fp16=torch.cuda.is_available(),
        logging_steps=10,
        save_strategy="epoch",
        evaluation_strategy="no",
        save_total_limit=2,
        report_to=["none"],
    )

    trainer = Seq2SeqTrainer(
        args=training_args,
        model=model,
        train_dataset=train_dataset,
        data_collator=data_collator,
        tokenizer=processor.feature_extractor,
    )

    logger.info("Starting training loop...")
    trainer.train()

    # Save final model & processor artifacts
    model.save_pretrained(output_dir)
    processor.save_pretrained(output_dir)
    logger.info(f"Model successfully fine-tuned and saved to {output_dir}")
    return model, processor


def train_sarvam_causal_lm(
    dataset_jsonl: str,
    output_dir: str = "./models/sarvam-indic-finetuned",
    model_id: str = "sarvamai/sarvam-1",
    batch_size: int = 2,
    learning_rate: float = 5e-5,
    num_epochs: int = 3,
    max_samples: Optional[int] = None,
):
    """Fine-tunes Sarvam-1 Indic LM on Indic/Code-Switched conversational texts."""
    import torch
    from datasets import Dataset
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    logger.info(f"--- Initializing Sarvam-1 Indic LM Fine-Tuning ({model_id}) ---")

    hf_token = os.getenv("HUGGINGFACE_HUB_TOKEN")
    tokenizer = AutoTokenizer.from_pretrained(model_id, token=hf_token)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        token=hf_token,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        low_cpu_mem_usage=True,
    )

    texts = []
    with open(dataset_jsonl, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if max_samples and i >= max_samples:
                break
            record = json.loads(line.strip())
            texts.append(record.get("text", ""))

    logger.info(f"Loaded {len(texts)} text samples for Sarvam-1 fine-tuning.")

    def tokenize_function(examples):
        return tokenizer(examples["text"], truncation=True, max_length=512)

    raw_dataset = Dataset.from_dict({"text": texts})
    tokenized_dataset = raw_dataset.map(tokenize_function, batched=True, remove_columns=["text"])

    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    training_args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=learning_rate,
        num_train_epochs=num_epochs,
        fp16=torch.cuda.is_available(),
        logging_steps=10,
        save_strategy="epoch",
        report_to=["none"],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=data_collator,
    )

    logger.info("Starting Sarvam-1 fine-tuning...")
    trainer.train()

    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    logger.info(f"Sarvam-1 fine-tuned weights saved to {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="ABCI-MI Model Fine-Tuning CLI")
    parser.add_argument("--model_type", required=True, choices=["whisper", "sarvam"], help="Target model architecture")
    parser.add_argument("--train_file", required=True, help="Input manifest JSONL path")
    parser.add_argument("--output_dir", required=True, help="Directory to save fine-tuned model")
    parser.add_argument("--model_id", default="", help="Hugging Face model ID (e.g. openai/whisper-large-v3 or sarvamai/sarvam-1)")
    parser.add_argument("--language", default="zh", help="Target language code (zh for AISHELL-1, hi for YODAS2, en for AMI)")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=4, help="Per-device batch size")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate")
    parser.add_argument("--max_samples", type=int, default=None, help="Cap training samples for quick runs")

    args = parser.parse_args()

    if args.model_type == "whisper":
        model_id = args.model_id or "openai/whisper-large-v3"
        train_whisper_lora(
            dataset_jsonl=args.train_file,
            output_dir=args.output_dir,
            model_id=model_id,
            language=args.language,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            num_epochs=args.epochs,
            max_samples=args.max_samples,
        )
    elif args.model_type == "sarvam":
        model_id = args.model_id or "sarvamai/sarvam-1"
        train_sarvam_causal_lm(
            dataset_jsonl=args.train_file,
            output_dir=args.output_dir,
            model_id=model_id,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            num_epochs=args.epochs,
            max_samples=args.max_samples,
        )


if __name__ == "__main__":
    main()
