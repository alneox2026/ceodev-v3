# DESIGN_SPEC.md

## Overview
Maxima is a single AI agent designed to provide accurate answers to general user questions. It determines when to rely on internal knowledge and when to use external Google search, optimizing for cost and speed.

## Example Use Cases
- "What is the capital of France?" -> Uses internal knowledge.
- "What are the latest AI news today?" -> Uses google_search tool.

## Tools Required
- `google_search`: Built-in ADK tool to perform web searches for fresh data.

## Constraints & Safety Rules
- Must give truthful, accurate answers.
- No hallucinated or made up answers.
- MUST minimize the use of `google_search` to save costs, using it only for fresh/recent information.

## Success Criteria
- Accurately answers questions.
- Successfully limits tool usage to appropriate scenarios.
- Handles multiple concurrent requests asynchronously.
- Deployable to Agent Runtime for access via FlutterFlow API calls.
