"""Worker entrypoint: registers the AI literacy classification pipeline workflow.

In a managed deployment the platform injects DEPLOYMENT_NAME, SERVER_URL and the
service-account token file (MISTRAL_SA_TOKEN_PATH); no API key lives in the repo.
"""
import asyncio

import mistralai.workflows as workflows

from classification.pipeline import AiLiteracyClassificationWorkflow


async def main() -> None:
    await workflows.run_worker([AiLiteracyClassificationWorkflow])


if __name__ == "__main__":
    asyncio.run(main())
