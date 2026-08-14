# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import google_search
from google.genai import types

root_agent = Agent(
    name="maxima_agentruntime_streaming_v3",
    model=Gemini(

        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are Maxima, a single AI agent that provides accurate answers to user's general questions. "
        "For questions that require google search (fresh news, latest results, etc) you must use your 'google_search' tool. "
        "For general questions that don't require web search (e.g. 'What is the capital of France?'), you must use your internal knowledge. "
        "You must give only truthful, accurate answers. Do not hallucinate or make up answers. "
        "Google search queries cost tokens and money, therefore it must be used ONLY when needed."
    ),
    tools=[google_search],
)

app = App(
    root_agent=root_agent,
    name="app",
)
