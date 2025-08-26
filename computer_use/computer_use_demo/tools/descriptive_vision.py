import asyncio
import os
import base64
from anthropic.types.beta import BetaMessageParam
from openai import OpenAI
from pathlib import Path
from uuid import uuid4

from .base import BaseLLMTool, ToolError, ToolResult
from .run import run

SCREENSHOT_DIR = '/tmp/screenshots'

### XXX: Huge ad-hoc, that require huge redesign,
## Tools are intended to recieve arguments only from LLM that called them
## And while it possible to handle this specific tool and additionally pass
## client variable in chat_loop, I prefer to localize this design fault in single file
## This tool should not exist, this app should be used with multimodal tool capable LLM
## This is excactly that case when bodge lives up to prod despite it MUSTN'T
##
## Maybe one day, this project will have global state object to keep stuff like `client`
## available across files, but for now I have to re-init it here
## And while st.session_state could be this object, I would like to store there only
## frontend-related stuff as streamlit is a frontend-oriented framework
_client = OpenAI(
        base_url="https://api.studio.nebius.com/v1",
        api_key=os.environ.get('NEBIUS_API_KEY'),
        max_retries=4
    )

## Qwen, because it's default for nebius, and probably they'll have beter interaction
## 2 instead of 2.5 because it's cheaper :)
VISION_MODEL="Qwen/Qwen2-VL-72B-Instruct"
VISION_MODEL_SYSTEM_PROMPT = """
* You are vision provider for another model, that can't process images by themself
* Together you are controlling Ubuntu virtual machine with GUI
* Your goal is to answer the other model's question about provided screenshot and images
* You interact only with model, so feel free to pack information in any way, until it understandable for LLM
* While describing images, focus on answering question, but do not hesitate to add additional information, anything that you deem valuable, like interactive elements.
* While descrbing any interactive elements, such as buttons, sliders, text entries add their coordinates, so model could interact with them by clicking and typing.
* While describing website content, put attention to anything odd on page, this is very valuable
* You can ask your partner-model to scroll website content for you
"""
system_msg = BetaMessageParam(
    role="system",
    content=VISION_MODEL_SYSTEM_PROMPT,
)

class DescriptiveVision(BaseLLMTool):
    """
    A tool that takes a screenshot and feeds it to vision-capable LLM
    with given prompt. and return LLM's answer. 
    Intentionally don't have valid Anthropic serialization 
    as Anthropic models must use computer tool
    Important: This tool is dictionary example of abomination,
    If you want to know why, read the source
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
        question_msg = {
            'role': 'user',
            'content': [{
                'type': 'text',
                'text': prompt
            },
            {
                'type': 'image_url',
                'image_url': {
                    'url': 'data:image/png;base64,'+base64_image
                }
            }]
        }
        raw_response = _client.chat.completions.with_raw_response.create(
            max_tokens=4096,
            messages=[system_msg, question_msg],
            model=VISION_MODEL,
        )

        response = raw_response.parse()
        answer = response.choices[0].message.content
        return ToolResult(output=answer, error=None, base64_image=base64_image)
        ## Temporary (or not) mock with zenity and user-as-llm
        ## In case, you don't use Nebius, but still need this tool WTF?!
        ## Comment/remove first return line and let code flow with your vibes (gross!)
        zenity_cmd = f'DISPLAY=:1 zenity --entry --text="{prompt}"'
        _, stdout, stderr = await run(zenity_cmd, timeout=300.0)
        return ToolResult(output=stdout, error=stderr, base64_image=base64_image)

