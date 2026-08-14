# ruff: noqa
"""Cloud Run canary variant of the Maxima ADK agent."""

from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import google_search
from google.genai import types


MAXIMA_MODEL = os.getenv("MAXIMA_MODEL", "gemini-2.5-flash")

root_agent = Agent(
    name="maxima_cloudrun_v3",
    model=Gemini(

        model=MAXIMA_MODEL,
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
