import base64
import json
import os
import io
from typing import List, Dict, Any, Union
from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv
from PIL import Image
from tenacity import retry, wait_exponential, stop_after_attempt

from schemas import (
    CommonPolicyList, FunctionDefinitionData, DuplicateList, TestCaseList
)
from prompts import (
    COMMON_POLICY_SYSTEM_PROMPT, get_function_definition_prompt, 
    SEMANTIC_DUPLICATES_PROMPT, TEST_CASES_PROMPT
)

load_dotenv()
aclient = AsyncOpenAI()
client = OpenAI()

def encode_image(image_path: str) -> str:
    """이미지를 읽고, 크기가 크면 리사이징 후 base64로 인코딩합니다."""
    with Image.open(image_path) as img:
        max_size = 2000
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

def extract_common_policy(image_paths: List[str]) -> Dict:
    messages = [
        {"role": "system", "content": COMMON_POLICY_SYSTEM_PROMPT},
        {"role": "user", "content": [{"type": "text", "text": "다음 이미지들에서 공통 정책을 추출해주세요."}]}
    ]
    
    for img_path in image_paths:
        base64_image = encode_image(img_path)
        messages[1]["content"].append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{base64_image}", "detail": "high"}
        })
        
    response = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=messages,
        temperature=0.1,
        response_format=CommonPolicyList
    )
    return response.choices[0].message.parsed.model_dump()

@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(3))
async def async_extract_function_definition(image_path: str, slide_number: int, common_policy: str) -> Dict:
    system_prompt = get_function_definition_prompt(slide_number, common_policy)
    base64_image = encode_image(image_path)
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [
            {"type": "text", "text": "제공된 화면 이미지를 분석하여 기능 정의서를 작성해주세요."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}", "detail": "high"}}
        ]}
    ]
    
    response = await aclient.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=messages,
        temperature=0.1,
        response_format=FunctionDefinitionData
    )
    return response.choices[0].message.parsed.model_dump()

def find_semantic_duplicates(flat_functions: List[Dict]) -> Dict:
    messages = [
        {"role": "system", "content": SEMANTIC_DUPLICATES_PROMPT},
        {"role": "user", "content": f"다음 기능 목록을 분석하여 중복 그룹을 찾아주세요:\n{json.dumps(flat_functions, ensure_ascii=False)}"}
    ]
    
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini-2024-07-18",
        messages=messages,
        temperature=0.1,
        response_format=DuplicateList
    )
    return response.choices[0].message.parsed.model_dump()

def generate_test_cases(function_definition: List[Dict]) -> Dict:
    messages = [
        {"role": "system", "content": TEST_CASES_PROMPT},
        {"role": "user", "content": f"다음 승인 완료된 기능 정의서를 바탕으로 테스트 케이스를 생성해:\n\n{json.dumps(function_definition, ensure_ascii=False)}"}
    ]
    
    response = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=messages,
        temperature=0.1,  # 논리적 일관성을 위해 낮게 유지
        response_format=TestCaseList
    )
    return response.choices[0].message.parsed.model_dump()
