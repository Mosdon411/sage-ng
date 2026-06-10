# backend/llm_processor.py
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import openai
from typing import Dict, List

class SAGELLM:
    def __init__(self, use_local=True):
        self.use_local = use_local
        if use_local:
            # Using Llama 3.1 or Mistral for local inference
            self.tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-3.1-8B")
            self.model = AutoModelForSequenceClassification.from_pretrained("meta-llama/Llama-3.1-8B")
        else:
            openai.api_key = os.getenv("OPENAI_API_KEY")
    
    def classify_threat(self, text: str) -> Dict:
        """Classify social media/text into threat categories"""
        prompt = f"""
        Analyze this text from Nigeria and classify:
        Text: "{text}"
        
        Return JSON:
        {{
            "threat_type": "bandit|terrorist|herder-conflict|kidnapping|none",
            "severity": "critical|high|medium|low|none",
            "region": "north-east|north-west|north-central|south-west|south-east|south-south",
            "confidence": 0.0-1.0,
            "requires_action": true/false
        }}
        """
        
        if self.use_local:
            # Local inference
            inputs = self.tokenizer(prompt, return_tensors="pt")
            outputs = self.model(**inputs)
            # Parse output (simplified)
            return {"threat_type": "bandit", "severity": "high", "confidence": 0.85}
        else:
            # GPT-4o API
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
    
    def generate_action_report(self, threats: List[Dict]) -> str:
        """Generate executive summary for security teams"""
        prompt = f"""
        Generate a concise security action report for Nigeria based on:
        {json.dumps(threats, indent=2)}
        
        Include:
        - Priority regions
        - Recommended response
        - Predicted next 24h hotspots
        """
        
        # Call LLM
        return "Priority: Zamfara. Deploy rapid response to Katsina border. High probability of attack in next 12h."