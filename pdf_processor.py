import fitz
import os
from typing import List, Tuple

def validate_pdf(pdf_path: str) -> Tuple[bool, str]:
    """
    Checks if the PDF has text layers.
    Returns (is_valid, warning_message).
    """
    try:
        doc = fitz.open(pdf_path)
        total_text = ""
        # Check first 5 pages or all if less than 5
        pages_to_check = min(5, len(doc))
        for i in range(pages_to_check):
            page = doc[i]
            total_text += page.get_text()
        
        doc.close()
        
        if len(total_text.strip()) < 20:
            return False, "스캔된 이미지나 저화질 문서의 경우 분석 품질이 크게 저하될 수 있습니다. 가능하면 설계 도구에서 직접 내보낸 원본 피디에프를 사용해 주세요."
        return True, ""
    except Exception as e:
        return False, f"PDF 파일을 읽을 수 없습니다: {str(e)}"

def pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 300, progress_callback=None) -> List[str]:
    """
    Converts a PDF file to a list of high-resolution images (one per page).
    Saves images to output_dir and returns a list of image paths.
    """
    image_paths = []
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        for page_num in range(total_pages):
            page = doc[page_num]
            # Convert to image with specified DPI
            pix = page.get_pixmap(dpi=dpi)
            
            img_path = os.path.join(output_dir, f"page_{page_num + 1}.png")
            pix.save(img_path)
            image_paths.append(img_path)
            
            if progress_callback:
                progress_callback(page_num + 1, total_pages)
                
        doc.close()
    except Exception as e:
        raise RuntimeError(f"PDF 변환 중 오류가 발생했습니다: {str(e)}")
        
    return image_paths
