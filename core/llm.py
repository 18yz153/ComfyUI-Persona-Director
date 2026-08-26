import json
import re

from openai import OpenAI


def robust_json_parse(raw):
    """Extract and parse JSON from a raw LLM response (handles code fences)."""
    if not raw:
        return None
    try:
        return json.loads(raw.strip())
    except Exception:
        pass
    m = re.search(r"(\{.*\})", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return None


class LLMBackend:
    """Thin wrapper over the OpenAI-compatible chat completions API.

    All backends (OpenAI, LM Studio, OpenRouter, DeepSeek, Gemini, vLLM,
    Ollama) speak this protocol. Tool calls degrade gracefully to plain JSON
    when the model or provider cannot do function calling.
    """

    def __init__(self, api_url, api_key, model_name):
        self.client = OpenAI(base_url=api_url, api_key=api_key)
        self.model_name = model_name

    def complete(self, system_prompt, user_message, tools=None, tool_mode="auto"):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        kwargs = {"model": self.model_name, "messages": messages, "temperature": 0.5}

        use_tools = bool(tools) and tool_mode != "json_only"
        if use_tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"  # string only: LM Studio rejects object form

        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception:
            if use_tools and tool_mode == "auto":
                # Provider rejected tools -> retry without them (JSON echo path).
                kwargs.pop("tools", None)
                kwargs.pop("tool_choice", None)
                resp = self.client.chat.completions.create(**kwargs)
            else:
                raise

        return self._parse(resp)

    def _parse(self, resp):
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            raise RuntimeError("LLM output truncated (max tokens reached).")
        if choice.finish_reason == "content_filter":
            raise RuntimeError("LLM refused to generate (content filter).")

        msg = choice.message
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            args = tool_calls[0].function.arguments
            data = robust_json_parse(args)
            if data is None:
                raise RuntimeError("Failed to parse tool-call arguments: %s" % str(args)[:200])
            return data

        data = robust_json_parse(msg.content)
        if data is None:
            raise RuntimeError("Failed to parse LLM response: %s" % str(msg.content)[:200])
        return data
