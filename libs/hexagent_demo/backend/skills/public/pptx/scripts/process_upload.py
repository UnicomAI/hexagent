# -*- coding: utf-8 -*-
import os
import json
import shutil
import fitz  # PyMuPDF
import argparse
from typing import List, Dict, Any

class UserSourceFileParser:
    def __init__(self):
        pass

    def parse(self, input_dir: str, target_dir: str) -> str:
        input_dir = os.path.abspath(input_dir)
        target_dir = os.path.abspath(target_dir)
        if not os.path.exists(input_dir):
            return f"失败：输入目录不存在 {input_dir}"
        os.makedirs(target_dir, exist_ok=True)
        image_root = os.path.join(target_dir, "image")
        os.makedirs(image_root, exist_ok=True)

        resource_list = []
        files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
        user_uploaded_images = []

        for filename in files:
            file_path = os.path.join(input_dir, filename)
            ext = os.path.splitext(filename)[1].lower()
            base_name = os.path.splitext(filename)[0]
            print(f"  [Parser] 📂 Processing: {filename}...", end="", flush=True)
            if ext == ".pdf":
                if self._parse_pdf(file_path, target_dir, image_root):
                    resource_list.extend([f"{base_name}.md", f"image_{base_name}.json"])
                    print(" DONE ✅")
                else:
                    print(" FAILED ❌")
            elif ext == ".txt":
                shutil.copy2(file_path, os.path.join(target_dir, filename))
                resource_list.append(filename)
                print(" DONE ✅")
            elif ext in [".jpg", ".jpeg", ".png", ".svg"]:
                user_uploaded_images.append(file_path)
                print(" QUEUED (Image Batch) 📥")

        if user_uploaded_images:
            print(f"  [Parser] 🖼️ Handling {len(user_uploaded_images)} user images...", end="", flush=True)
            if self._handle_user_images(user_uploaded_images, target_dir, image_root):
                resource_list.append("image_user_upload.json")
                print(" DONE ✅")
            else:
                print(" FAILED ❌")

        return f"成功：文件处理完成。\n目标文件夹: {target_dir}\n清单: {', '.join(resource_list)}"

    def _parse_pdf(self, file_path, target_dir, image_root):
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        pdf_img_dir = os.path.join(image_root, base_name)
        os.makedirs(pdf_img_dir, exist_ok=True)
        md_content, image_tasks = [], []
        try:
            doc = fitz.open(file_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                md_content.append(page.get_text())
                for img_idx, img in enumerate(page.get_images()):
                    image_filename = f"p{page_num+1}_i{img_idx+1}.png"
                    save_path = os.path.join(pdf_img_dir, image_filename)
                    pix = fitz.Pixmap(doc, img[0])
                    pix.save(save_path)
                    image_tasks.append({"save_path": save_path, "rel_path": f"image/{base_name}/{image_filename}", "idx": len(md_content)})
                    md_content.append(f"IMAGE_PLACEHOLDER_{len(image_tasks)-1}")
            self._finalize_md(md_content, image_tasks, target_dir, base_name)
            return True
        except Exception as e:
            print(f" PDF Error: {e}", end="")
            return False

    def _handle_user_images(self, image_paths, target_dir, image_root):
        image_metadata = []
        try:
            for path in image_paths:
                name = os.path.basename(path)
                dest = os.path.join(image_root, name)
                shutil.copy2(path, dest)
                image_metadata.append({
                    "name": name, 
                    "description": "请使用MCP视觉工具补充图片描述", 
                    "local_rel_path": f"image/{name}"
                })
            with open(os.path.join(target_dir, "image_user_upload.json"), "w", encoding="utf-8") as f:
                json.dump(image_metadata, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f" Image Error: {e}", end="")
            return False

    def _finalize_md(self, md_content, image_tasks, target_dir, base_name):
        image_metadata = []
        for i, t in enumerate(image_tasks):
            desc = "请使用MCP视觉工具补充图片描述"
            image_metadata.append({"description": desc, "local_rel_path": t["rel_path"]})
            placeholder = f"IMAGE_PLACEHOLDER_{i}"
            for idx, c in enumerate(md_content):
                if c == placeholder:
                    md_content[idx] = f"\n![{desc}]({t['rel_path']})\n"
                    break
        with open(os.path.join(target_dir, f"{base_name}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(md_content))
        with open(os.path.join(target_dir, f"image_{base_name}.json"), "w", encoding="utf-8") as f:
            json.dump(image_metadata, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    p = UserSourceFileParser()
    print(p.parse(args.input, args.output))
