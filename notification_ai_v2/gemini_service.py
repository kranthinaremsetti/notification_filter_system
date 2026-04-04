from __future__ import annotations

import json
import re
from typing import Any

import httpx

from config import Settings


SPAM_TOKENS = {"win cash", "click now", "free money", "lottery", "urgent action"}
IMPORTANT_TOKENS = {"otp", "verification code", "bank", "payment", "security alert", "transaction"}
AD_TOKENS = {"offer", "sale", "discount", "deal", "promo", "coupon", "cashback"}


class GeminiDecisionEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    def decide(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.gemini_api_key:
            return self._fallback(payload, context, "Missing GEMINI_API_KEY")

        prompt = self._build_prompt(payload, context)
        try:
            response = self._call_gemini(prompt)
            decision = self._parse_response(response)
            decision["source"] = "gemini"
            decision["gemini_raw"] = response
            return decision
        except Exception as exc:
            return self._fallback(payload, context, f"Gemini fallback: {exc}")

    def _call_gemini(self, prompt: str) -> dict[str, Any]:
        params = {"key": self.settings.gemini_api_key}

        body = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt,
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        candidate_models = [
            self.settings.gemini_model,
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash-latest",
        ]

        tried: list[str] = []
        with httpx.Client(timeout=self.settings.request_timeout_seconds) as client:
            for model in candidate_models:
                if not model or model in tried:
                    continue
                tried.append(model)

                model_path = f"{self.settings.gemini_api_url}/{model}:generateContent"
                res = client.post(model_path, params=params, json=body)
                if res.status_code == 404:
                    continue

                res.raise_for_status()
                data = res.json()
                data["_model_used"] = model
                return data

        raise ValueError(f"No Gemini model resolved from candidates: {', '.join(tried)}")

    def _parse_response(self, response: dict[str, Any]) -> dict[str, Any]:
        text = (
            response.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )

        parsed = self._extract_json(text)

        action = str(parsed.get("action", "SHOW")).upper().strip()
        if action not in {"SHOW", "DELAY", "BLOCK"}:
            action = "SHOW"

        confidence = parsed.get("confidence")
        try:
            confidence = float(confidence) if confidence is not None else None
        except Exception:
            confidence = None

        suggested_delay = parsed.get("suggested_delay_minutes")
        try:
            suggested_delay = int(suggested_delay) if suggested_delay is not None else None
        except Exception:
            suggested_delay = None

        reason = str(parsed.get("reason", "Gemini decision"))[:400]
        category = str(parsed.get("category", "normal")).strip().lower() or "normal"

        reason_tags = parsed.get("reason_tags") or []
        if not isinstance(reason_tags, list):
            reason_tags = []
        reason_tags = [str(tag).strip().lower() for tag in reason_tags if str(tag).strip()]

        return {
            "action": action,
            "reason": reason,
            "confidence": confidence,
            "suggested_delay_minutes": suggested_delay,
            "category": category,
            "reason_tags": reason_tags,
        }

    def _extract_json(self, text: str) -> dict[str, Any]:
        if not text:
            raise ValueError("Empty Gemini response")

        # Most responses should already be JSON due to responseMimeType.
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        # Backup parser if model wraps JSON in markdown.
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("No JSON object found in Gemini response")

        data = json.loads(match.group(0))
        if not isinstance(data, dict):
            raise ValueError("Gemini JSON is not an object")
        return data

    def _build_prompt(self, payload: dict[str, Any], context: dict[str, Any]) -> str:
        return (
            "You are a STRICT and FAST notification classifier.\n"
            "You must return ONLY valid JSON.\n\n"

            "OUTPUT FORMAT (STRICT):\n"
            "{"
            "\"action\":\"SHOW|DELAY|BLOCK\","
            "\"reason\":\"short reason\","
            "\"confidence\":0.0-1.0,"
            "\"suggested_delay_minutes\":integer,"
            "\"category\":\"important|spam|promotional|normal\","
            "\"reason_tags\":[\"tag1\",\"tag2\"]"
            "}\n\n"

            "DECISION RULES (STRICT PRIORITY ORDER):\n"

            "1) IMPORTANT → ALWAYS SHOW (NO DELAY):\n"
            "- otp, verification code, bank, transaction, payment, security alert\n"
            "- Example: 'Your OTP is 123456' → SHOW\n\n"

            "2) SPAM / SCAM → ALWAYS BLOCK (AGGRESSIVE):\n"
            "- lottery, win money, free money, click link, claim now, urgent prize\n"
            "- suspicious links or unknown offers\n"
            "- Example: 'You won 1000000 click link now' → BLOCK\n\n"

            "3) PROMOTIONAL → DELAY:\n"
            "- sale, discount, offer, cashback, deal, promo\n\n"

            "4) CONTEXT RULE:\n"
            "- If user is busy → DELAY everything except important\n\n"

            "5) NORMAL PERSONAL MESSAGES:\n"
            "- chats, personal messages → SHOW\n\n"

            "STRICT CONSTRAINTS:\n"
            "- NEVER delay important notifications\n"
            "- NEVER show obvious spam\n"
            "- DELAY only for promotional or busy cases\n"
            "- suggested_delay_minutes:\n"
            "    SHOW/BLOCK → 0\n"
            "    DELAY → 10-30 minutes\n"
            "- confidence must be between 0 and 1\n"
            "- NO explanations outside JSON\n\n"

            "FEW-SHOT EXAMPLES:\n"

            "Input: 'Your OTP is 123456'\n"
            "Output: {\"action\":\"SHOW\",\"reason\":\"OTP detected\",\"confidence\":0.99,\"suggested_delay_minutes\":0,\"category\":\"important\",\"reason_tags\":[\"otp\"]}\n\n"

            "Input: 'You won lottery click link now'\n"
            "Output: {\"action\":\"BLOCK\",\"reason\":\"lottery scam\",\"confidence\":0.99,\"suggested_delay_minutes\":0,\"category\":\"spam\",\"reason_tags\":[\"scam\"]}\n\n"

            "Input: 'Flat 50% discount sale today'\n"
            "Output: {\"action\":\"DELAY\",\"reason\":\"promotional content\",\"confidence\":0.9,\"suggested_delay_minutes\":15,\"category\":\"promotional\",\"reason_tags\":[\"ad\"]}\n\n"

            "Input: 'Hey are you free?'\n"
            "Output: {\"action\":\"SHOW\",\"reason\":\"personal message\",\"confidence\":0.85,\"suggested_delay_minutes\":0,\"category\":\"normal\",\"reason_tags\":[\"chat\"]}\n\n"

            f"Notification: {json.dumps(payload, ensure_ascii=True)}\n"
            f"Context: {json.dumps(context, ensure_ascii=True)}\n"
        )
    def _fallback(self, payload: dict[str, Any], context: dict[str, Any], reason: str) -> dict[str, Any]:
        text = f"{payload.get('title', '')} {payload.get('message', '')}".lower().strip()
        is_busy = bool(context.get("is_busy", False))

        has_important = any(token in text for token in IMPORTANT_TOKENS)
        has_spam = any(token in text for token in SPAM_TOKENS)
        has_ad = any(token in text for token in AD_TOKENS)

        # Spam should dominate unless the message is clearly critical (OTP/banking/security).
        if has_spam and not has_important:
            return {
                "action": "BLOCK",
                "reason": "Spam-like content detected",
                "confidence": 0.72,
                "suggested_delay_minutes": None,
                "category": "spam",
                "reason_tags": ["spam"],
                "source": "fallback",
                "gemini_raw": {"fallback_reason": reason},
            }

        if has_important:
            return {
                "action": "SHOW",
                "reason": "Important content detected",
                "confidence": 0.75,
                "suggested_delay_minutes": None,
                "category": "important",
                "reason_tags": ["important"],
                "source": "fallback",
                "gemini_raw": {"fallback_reason": reason},
            }

        if has_ad:
            return {
                "action": "DELAY",
                "reason": "Promotional content detected",
                "confidence": 0.65,
                "suggested_delay_minutes": 20 if is_busy else 10,
                "category": "ad",
                "reason_tags": ["ad"],
                "source": "fallback",
                "gemini_raw": {"fallback_reason": reason},
            }

        if is_busy:
            return {
                "action": "DELAY",
                "reason": "User currently unavailable",
                "confidence": 0.55,
                "suggested_delay_minutes": 10,
                "category": "normal",
                "reason_tags": ["busy"],
                "source": "fallback",
                "gemini_raw": {"fallback_reason": reason},
            }

        return {
            "action": "SHOW",
            "reason": "No strong risk signal",
            "confidence": 0.55,
            "suggested_delay_minutes": None,
            "category": "normal",
            "reason_tags": ["default_show"],
            "source": "fallback",
            "gemini_raw": {"fallback_reason": reason},
        }
