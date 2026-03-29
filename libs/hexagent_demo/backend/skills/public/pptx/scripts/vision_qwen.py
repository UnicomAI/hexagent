# -*- coding: utf-8 -*-
"""
Qwen Vision Tool for PPTX Pro Skill
Provides image description capabilities using Qwen Vision model.

Usage:
    python vision_qwen.py --image path/to/image.png --prompt "Describe this slide"
    python vision_qwen.py --images img1.png img2.png img3.png
"""

import argparse
import requests
import base64
import os
import sys
import json
import re
import time
from typing import Optional, List

# Try to import from utils/config.py in parent project, fallback to defaults
try:
    # Add parent paths to find config
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'metierial', 'utils', 'config.py')
    if os.path.exists(config_path):
        sys.path.insert(0, os.path.dirname(config_path))
        from config import QWEN_KEY, LLM_API_URL
    else:
        raise ImportError("Config not found")
except ImportError:
    # Default API configuration
    QWEN_KEY = "sk-1b897ac944044d6aae35ca862a23fbdb"
    LLM_API_URL = "https://maas-api.ai-yuanjing.com/openapi/compatible-mode-nosensitive/v1/chat/completions"


class QwenVisionTool:
    """Qwen Vision API wrapper for image description"""

    def __init__(self):
        self.api_key = QWEN_KEY
        self.url = LLM_API_URL

    def _prepare_image_data(self, image_path: str) -> Optional[str]:
        """Convert image to base64, SVG is converted to PNG first"""
        target_path = image_path
        temp_png = None
        try:
            if image_path.lower().endswith(".svg"):
                try:
                    from svglib.svglib import svg2rlg
                    from reportlab.graphics import renderPM
                    import tempfile
                    drawing = svg2rlg(image_path)
                    fd, temp_png = tempfile.mkstemp(suffix=".png")
                    os.close(fd)
                    renderPM.drawToFile(drawing, temp_png, fmt="PNG")
                    target_path = temp_png
                except ImportError:
                    print("Warning: svglib not installed, cannot convert SVG")
                    return None

            with open(target_path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except Exception as e:
            print(f"Error processing image {image_path}: {e}")
            return None
        finally:
            if temp_png and os.path.exists(temp_png):
                try:
                    os.remove(temp_png)
                except:
                    pass

    def describe_images_batch(self, image_paths: List[str], prompt: str = "请详细描述这些图片的内容。") -> List[str]:
        """
        Batch describe images, up to 5 images per request.
        """
        results = []
        # Group by max 5 images
        for i in range(0, len(image_paths), 5):
            batch = image_paths[i:i+5]
            batch_results = self._call_qwen_vision_batch(batch, prompt)
            results.extend(batch_results)
            # 1 second interval between batches
            if i + 5 < len(image_paths):
                time.sleep(1)
        return results

    def _call_qwen_vision_batch(self, image_paths: List[str], prompt: str) -> List[str]:
        """Send a single batch (max 5 images) to Qwen Vision API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        json_format_instruction = (
            "\n请严格按照以下 JSON 数组格式返回每张图片的描述内容，严禁包含任何额外的 Markdown 标记、解释性文字或示例内容：\n"
            "[\"描述1\", \"描述2\", ...]\n"
            f"注意：你必须提供正好 {len(image_paths)} 个字符串，每个字符串对应一张图片的详细描述。"
        )

        content = [{"type": "text", "text": f"{prompt} {json_format_instruction}"}]

        for path in image_paths:
            img_b64 = self._prepare_image_data(path)
            if img_b64:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                })
            else:
                content.append({"type": "text", "text": f"[无法读取图片: {os.path.basename(path)}]"})

        payload = {
            "model": "qwen3.5-397b-a17b",
            "messages": [{"role": "user", "content": content}],
            "stream": False,
            "response_format": {"type": "json_object"}
        }

        try:
            resp = requests.post(self.url, headers=headers, json=payload, timeout=120)
            if resp.status_code == 200:
                full_text = resp.json()["choices"][0]["message"]["content"]

                # Try to parse JSON
                descriptions = []
                try:
                    start_idx = full_text.find("[")
                    end_idx = full_text.rfind("]")
                    if start_idx != -1 and end_idx != -1:
                        json_str = full_text[start_idx:end_idx+1]
                        data = json.loads(json_str)
                        if isinstance(data, list):
                            descriptions = [str(d) for d in data]
                except:
                    pass

                # Fallback: regex matching
                if len(descriptions) < len(image_paths):
                    matches = re.findall(r'"([^"]+)"', full_text)
                    if len(matches) >= len(image_paths):
                        descriptions = matches

                # Filter invalid descriptions
                invalid_keywords = ["描述", "示例", "Image [", "图片"]
                final_descriptions = []
                for d in descriptions:
                    if len(d) < 20 and any(k in d for k in invalid_keywords):
                        continue
                    final_descriptions.append(d)

                if len(final_descriptions) >= len(image_paths):
                    return final_descriptions[:len(image_paths)]

                # Last resort: split by markers
                fallback_descs = []
                parts = re.split(r'Image \[\d+\]:|第\d+张图片:|^\d+\.', full_text)
                for p in parts:
                    clean_p = p.strip()
                    if len(clean_p) > 10:
                        fallback_descs.append(clean_p)

                if len(fallback_descs) >= len(image_paths):
                    return fallback_descs[:len(image_paths)]

                print(f"Warning: Could not extract valid descriptions. Output length: {len(full_text)}")
                return [full_text] * len(image_paths)
            else:
                return [f"API Error: {resp.status_code}"] * len(image_paths)
        except Exception as e:
            return [f"Request Exception: {e}"] * len(image_paths)

    def describe_image(self, image_path: str, prompt: str = "请详细描述这张图片的内容。") -> str:
        """Single image description (backward compatible)"""
        return self.describe_images_batch([image_path], prompt)[0]


def main():
    parser = argparse.ArgumentParser(description="Qwen Vision Tool for image description")
    parser.add_argument("--image", "-i", help="Single image path to describe")
    parser.add_argument("--images", "-I", nargs="+", help="Multiple image paths for batch description")
    parser.add_argument("--prompt", "-p", default="请详细描述这张/这些图片的内容。", help="Prompt for description")
    parser.add_argument("--output", "-o", help="Output file for results (JSON format for batch)")

    args = parser.parse_args()

    tool = QwenVisionTool()

    if args.image:
        result = tool.describe_image(args.image, args.prompt)
        print(f"\n描述结果:\n{result}")

    elif args.images:
        results = tool.describe_images_batch(args.images, args.prompt)
        print(f"\n批量描述结果:")
        for i, (path, desc) in enumerate(zip(args.images, results)):
            print(f"\n[{i+1}] {os.path.basename(path)}:")
            print(f"    {desc[:200]}..." if len(desc) > 200 else f"    {desc}")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(dict(zip(args.images, results)), f, ensure_ascii=False, indent=2)
            print(f"\n结果已保存到: {args.output}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
