import importlib
from typing import Optional, Tuple

assistant_modules = {
    "ai": "ai_prompts",
    "compliance": "compliance_prompt",
    "ecommerce": "ecommerce_prompts",
    "finance": "finance_prompt",
    "leadership": "leadership",
    "legal": "legal",
    "marketing": "marketing",
    "operations": "operations",
    "platform": "platform_prompt",
    "product": "product",
    "research": "research",
    "retail": "retail_prompts",
    "saas": "saas_prompt",
    "strategy": "strategy_prompts",
    "support": "support_prompt",
    "technical": "technical_prompt",
}

def select_assistant_context(text: str) -> Tuple[Optional[str], Optional[str]]:
    for keyword, module_name in assistant_modules.items():
        if keyword.lower() in text.lower():
            try:
                mod = importlib.import_module(f"app.assistants_prompt.{module_name}")
                if hasattr(mod, "PROMPT"):
                    return keyword, mod.PROMPT
            except Exception:
                pass
    return None, None
