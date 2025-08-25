import asyncio
import base64
from pathlib import Path
from uuid import uuid4

from .base import BaseLLMTool, ToolError, ToolResult
from .run import run

SCREENSHOT_DIR = '/tmp/screenshots'

class DescriptiveVision(BaseLLMTool):
    """
    A tool that takes a screenshot and feeds it to vision-capable LLM
    with given prompt. and return LLM's answer. 
    Intentionally don't have valid Anthropic serialization 
    as Anthropic models must use computer tool
    """

    def to_openai_params(self):
        return {
            "type": "function",
            "function": {
                "name": "descriptive-vision",
                "description": "Describes what is currently on screen or given image file. " \
                    "Can answer specific question",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Question to guide description process"
                        },
                        "image": {
                            "type": "string",
                            "description": "full path to image file that need description."
                        }
                    },
                    "required": ["prompt"]
                }
            }
        }

    def to_anthropic_params(self):
        return {'name': 'descriptive-vision'}

    async def __call__(
        self, prompt: str | None = None, image: str | None = None
    ):
        if prompt is None:
            raise ToolError("No prompt provided")
        if image is not None:
            path = Path(image)
            if not path.is_file():
                raise ToolError("Provided image is not an existing file")
        else:
            screenshot_dir = Path(SCREENSHOT_DIR)
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = screenshot_dir / f"screenshot_{uuid4().hex}.png"
            screenshot_cmd = f"DISPLAY=:1 scrot -p {path}"
            _, stdout, stderr = await run(screenshot_cmd)

        result = await self.get_description(prompt, path)
        return result

    async def get_description(self, prompt: str, path: str):
        base64_image=base64.b64encode(path.read_bytes()).decode()
        ## Temporary (or not) mock with zenity and user-as-llm
        zenity_cmd = f'DISPLAY=:1 zenity --entry --text="{prompt}"'
        _, stdout, stderr = await run(zenity_cmd, timeout=300.0)
        return ToolResult(output=stdout, error=stderr, base64_image=base64_image)

