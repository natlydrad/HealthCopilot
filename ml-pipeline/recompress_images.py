#!/usr/bin/env python3
"""
Recompress existing meal images in pb_data_clean/storage.
Resizes to max 1024px and compresses to 65% JPEG quality.

Run: python3 recompress_images.py
"""

import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Installing Pillow...")
    os.system("pip3 install Pillow")
    from PIL import Image

# Configuration - matches iOS app settings
MAX_DIMENSION = 1024
JPEG_QUALITY = 65

STORAGE_DIR = Path(__file__).parent.parent / "backend" / "pb_data_clean" / "storage"


def recompress_image(img_path: Path) -> tuple[int, int]:
    """Recompress a single image. Returns (original_size, new_size)."""
    original_size = img_path.stat().st_size
    
    with Image.open(img_path) as img:
        # Convert to RGB if needed (handles RGBA, palette, etc.)
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
        
        # Calculate new size preserving aspect ratio
        width, height = img.size
        ratio = min(MAX_DIMENSION / width, MAX_DIMENSION / height)
        
        if ratio < 1:
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        
        # Save with compression
        img.save(img_path, 'JPEG', quality=JPEG_QUALITY, optimize=True)
    
    new_size = img_path.stat().st_size
    return original_size, new_size


def main():
    if not STORAGE_DIR.exists():
        print(f"❌ Storage directory not found: {STORAGE_DIR}")
        return
    
    # Find all JPG files (excluding thumbnails which are already small)
    jpg_files = []
    for jpg in STORAGE_DIR.rglob("*.jpg"):
        # Skip thumbnails (they start with dimensions like "100x100_")
        if jpg.name.startswith(("100x100_", "200x200_", "thumb")):
            continue
        jpg_files.append(jpg)
    
    if not jpg_files:
        print("No images found to recompress.")
        return
    
    print(f"Found {len(jpg_files)} images to recompress...")
    print(f"Settings: max {MAX_DIMENSION}px, {JPEG_QUALITY}% quality\n")
    
    total_original = 0
    total_new = 0
    
    for i, img_path in enumerate(jpg_files, 1):
        try:
            orig, new = recompress_image(img_path)
            total_original += orig
            total_new += new
            
            savings = (1 - new / orig) * 100 if orig > 0 else 0
            print(f"[{i}/{len(jpg_files)}] {img_path.name}: {orig/1024:.0f}KB → {new/1024:.0f}KB ({savings:.0f}% smaller)")
        except Exception as e:
            print(f"[{i}/{len(jpg_files)}] ❌ {img_path.name}: {e}")
    
    print(f"\n{'='*50}")
    print(f"Total: {total_original/1024/1024:.1f}MB → {total_new/1024/1024:.1f}MB")
    print(f"Saved: {(total_original - total_new)/1024/1024:.1f}MB ({(1 - total_new/total_original)*100:.0f}% reduction)")


if __name__ == "__main__":
    main()
