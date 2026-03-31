# -*- coding: utf-8 -*-
"""
PPT to Image Converter for PPTX Plus Skill (Linux)
Converts PPTX slides to images for visual inspection.

Usage:
    python ppt_to_pic.py --ppt-dir ./ppt --output-dir ./images
    python ppt_to_pic.py --file presentation.pptx --output slide.png

Requirements:
    - LibreOffice with soffice available
    - Poppler (pdftoppm) for PDF to image conversion
"""

import argparse
import os
import sys
import time
from pathlib import Path


def ppt_to_pic_libreoffice(ppt_path: str, output_dir: str) -> bool:
    """Convert PPTX to images using LibreOffice (cross-platform)"""
    try:
        import subprocess

        abs_ppt_path = os.path.abspath(ppt_path)
        abs_output_dir = os.path.abspath(output_dir)
        os.makedirs(abs_output_dir, exist_ok=True)

        # First convert to PDF
        result = subprocess.run([
            "soffice", "--headless", "--convert-to", "pdf",
            "--outdir", abs_output_dir, abs_ppt_path
        ], capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            print(f"LibreOffice PDF conversion failed: {result.stderr}")
            return False

        # Get PDF path
        pdf_name = Path(ppt_path).stem + ".pdf"
        pdf_path = os.path.join(abs_output_dir, pdf_name)

        if not os.path.exists(pdf_path):
            print(f"PDF not found: {pdf_path}")
            return False

        # Convert PDF to images using pdftoppm
        result = subprocess.run([
            "pdftoppm", "-jpeg", "-r", "150", pdf_path,
            os.path.join(abs_output_dir, "slide")
        ], capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            print(f"pdftoppm failed: {result.stderr}")
            return False

        # Clean up PDF
        try:
            os.remove(pdf_path)
        except:
            pass

        return True

    except FileNotFoundError as e:
        print(f"Required tool not found: {e}")
        print("Please install LibreOffice and Poppler (pdftoppm)")
        return False
    except Exception as e:
        print(f"LibreOffice conversion failed: {e}")
        return False


def convert_pptx_to_images(ppt_path: str, output_dir: str) -> str:
    """Convert a single PPTX file to images"""
    abs_ppt_path = os.path.abspath(ppt_path)
    abs_output_dir = os.path.abspath(output_dir)

    if not os.path.exists(abs_ppt_path):
        return f"Error: PPTX file not found: {abs_ppt_path}"

    os.makedirs(abs_output_dir, exist_ok=True)

    base_name = Path(ppt_path).stem

    # Use LibreOffice for conversion (Linux)
    if ppt_to_pic_libreoffice(abs_ppt_path, abs_output_dir):
        return f"Successfully converted {ppt_path} to images in {abs_output_dir}"

    return f"Failed to convert {ppt_path}. Please ensure LibreOffice and Poppler (pdftoppm) are installed."


def convert_directory(ppt_dir: str, output_dir: str) -> str:
    """Convert all PPTX files in a directory to images"""
    abs_ppt_dir = os.path.abspath(ppt_dir.lstrip("/").lstrip("\\"))
    abs_output_dir = os.path.abspath(output_dir.lstrip("/").lstrip("\\"))

    if not os.path.exists(abs_ppt_dir):
        return f"Error: Directory not found: {abs_ppt_dir}"

    os.makedirs(abs_output_dir, exist_ok=True)

    ppt_files = [f for f in os.listdir(abs_ppt_dir)
                 if f.endswith('.pptx') and not f.startswith('~$')]

    if not ppt_files:
        return f"No PPTX files found in {abs_ppt_dir}"

    print(f"Converting {len(ppt_files)} PPTX files...")

    success_count = 0
    for filename in ppt_files:
        ppt_path = os.path.join(abs_ppt_dir, filename)
        print(f"  Processing: {filename}...", end="", flush=True)

        base_name = Path(filename).stem
        file_output_dir = os.path.join(abs_output_dir, base_name)

        if ppt_to_pic_libreoffice(ppt_path, file_output_dir):
            print(" DONE")
            success_count += 1
        else:
            print(" FAILED")

    return f"Successfully converted {success_count}/{len(ppt_files)} files to {abs_output_dir}"


def main():
    parser = argparse.ArgumentParser(description="Convert PPTX slides to images")
    parser.add_argument("--ppt-dir", "-d", help="Directory containing PPTX files")
    parser.add_argument("--file", "-f", help="Single PPTX file to convert")
    parser.add_argument("--output", "-o", help="Output directory or file path")

    args = parser.parse_args()

    if args.file:
        output = args.output or os.path.splitext(args.file)[0]
        result = convert_pptx_to_images(args.file, output)
        print(result)

    elif args.ppt_dir:
        output = args.output or os.path.join(args.ppt_dir, "images")
        result = convert_directory(args.ppt_dir, output)
        print(result)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
