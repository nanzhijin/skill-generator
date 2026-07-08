# Copyright 2026 Nan Zhijin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""LLM-powered skill generation — single-call, full automation."""

from skill_generator.llm.adapter import AnthropicAdapter, DeepSeekAdapter, LLMAdapter, create_adapter
from skill_generator.llm.parser import parse_llm_response, parse_robustness_response, ParseResult
from skill_generator.llm.prompts import SYSTEM_PROMPT, build_user_prompt

__all__ = [
    "LLMAdapter",
    "AnthropicAdapter",
    "DeepSeekAdapter",
    "create_adapter",
    "SYSTEM_PROMPT",
    "build_user_prompt",
    "parse_llm_response",
    "parse_robustness_response",
    "ParseResult",
]
