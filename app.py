import streamlit as st
import os
import json
import pandas as pd
from dotenv import load_dotenv

from file_manager import create_session_dir, save_uploaded_file, cleanup_session_dir
from pdf_processor import validate_pdf, pdf_to_images
from llm_service import extract_common_policy, async_extract_function_definition, generate_test_cases, find_semantic_duplicates
import asyncio
from excel_generator import generate_function_definition_excel, generate_test_case_excel
from enum import Enum
import logging
from typing import List, Dict, Any

# 로깅 설정
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load env variables (for OPENAI_API_KEY)
load_dotenv()

class AppStep(Enum):
    UPLOAD = 1
    SELECT = 2
    EXTRACT_POLICY = 3
    EXTRACT_FUNCTIONS = 4
    COMPLETE = 5

st.set_page_config(page_title="테스트 산출물 자동 생성 시스템", layout="wide")

def init_session_state() -> None:
    if "session_id" not in st.session_state:
        import uuid
        st.session_state.session_id = str(uuid.uuid4())
    if "session_dir" not in st.session_state:
        st.session_state.session_dir = create_session_dir(st.session_state.session_id)
    if "step" not in st.session_state:
        st.session_state.step = AppStep.UPLOAD.value
    if "image_paths" not in st.session_state:
        st.session_state.image_paths = []
    if "page_selections" not in st.session_state:
        st.session_state.page_selections = {}
    if "common_policy_text" not in st.session_state:
        st.session_state.common_policy_text = ""
    if "function_definitions" not in st.session_state:
        st.session_state.function_definitions = []
    if "test_cases_data" not in st.session_state:
        st.session_state.test_cases_data = None
    if "duplicate_clusters" not in st.session_state:
        st.session_state.duplicate_clusters = None

def reset_app() -> None:
    if "session_dir" in st.session_state:
        cleanup_session_dir(st.session_state.session_dir)
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

init_session_state()

# --- Header ---
col1, col2 = st.columns([4, 1])
with col1:
    st.title("테스트 산출물 자동 생성 시스템")
with col2:
    if st.button("처음부터 다시 분석하기 (초기화)", type="primary"):
        reset_app()

# --- Step 1: Upload ---
if st.session_state.step == AppStep.UPLOAD.value:
    uploaded_file = st.file_uploader("PDF 화면설계서를 업로드하여 기능명세서, 테스트 케이스로 변환하세요.", type=["pdf"])
    
    if uploaded_file is not None:
        with st.spinner("파일을 검증하고 변환 중입니다... (최대 1~2분 소요)"):
            pdf_path = save_uploaded_file(uploaded_file, st.session_state.session_dir)
            
            is_valid, warn_msg = validate_pdf(pdf_path)
            if not is_valid:
                st.warning(warn_msg)
                
            try:
                # Convert to images
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def update_progress(current, total):
                    progress_bar.progress(current / total)
                    status_text.text(f"PDF 페이지 추출 중... ({current}/{total} 페이지 완료)")

                image_paths = pdf_to_images(pdf_path, st.session_state.session_dir, progress_callback=update_progress)
                st.session_state.image_paths = image_paths
                st.session_state.step = AppStep.SELECT.value
                st.rerun()
            except Exception as e:
                logger.error("변환 중 오류 발생", exc_info=True)
                st.error(f"변환 오류: {str(e)}")

# --- Step 2: Categorization ---
elif st.session_state.step == AppStep.SELECT.value:
    st.subheader("슬라이드 솎아내기 및 분류")
    st.write("각 슬라이드의 역할을 선택해주세요. (공통 정책 / 분석 대상 화면 / 제외)")
    
    # 5-column grid
    cols = st.columns(5)
    for i, img_path in enumerate(st.session_state.image_paths):
        col = cols[i % 5]
        with col:
            st.image(img_path, caption=f"페이지 {i+1}", width="stretch")
            choice = st.radio(
                f"페이지 {i+1} 설정",
                options=["제외", "공통 정책", "분석 대상 화면"],
                key=f"page_{i}"
            )
            st.session_state.page_selections[i] = choice
            
    # Check if any "분석 대상 화면" is selected
    has_target = any(c == "분석 대상 화면" for c in st.session_state.page_selections.values())
    
    if st.button("선택 완료 및 공통 정책 추출 시작", disabled=not has_target):
        st.session_state.step = AppStep.EXTRACT_POLICY.value
        st.rerun()
    if not has_target:
        st.caption("최소 1개 이상의 '분석 대상 화면'을 선택해야 진행할 수 있습니다.")

# --- Step 3: Extract Common Policy ---
elif st.session_state.step == AppStep.EXTRACT_POLICY.value:
    st.subheader("공통 정책 추출 및 검수")
    
    policy_indices = [i for i, c in st.session_state.page_selections.items() if c == "공통 정책"]
    
    if not st.session_state.common_policy_text:
        if not policy_indices:
            st.session_state.common_policy_text = "선택된 공통 정책 페이지가 없습니다."
        else:
            with st.spinner("공통 정책을 추출하는 중입니다..."):
                policy_images = [st.session_state.image_paths[i] for i in policy_indices]
                result = extract_common_policy(policy_images)
                
                if isinstance(result, dict):
                    # Format dict to text
                    text_result = f"프로젝트명: {result.get('프로젝트명', '')}\n\n[공통 정책 목록]\n"
                    for p in result.get('공통_정책_목록', []):
                        text_result += f"- {p}\n"
                    st.session_state.common_policy_text = text_result
                else:
                    st.session_state.common_policy_text = str(result)
                    st.warning("결과를 표 구조로 변환하는 데 실패했습니다. 원본 텍스트를 바탕으로 검수해 주세요.")
            st.rerun()
            
    # User edits the policy
    edited_policy = st.text_area("공통 정책 (수정 가능)", value=st.session_state.common_policy_text, height=300)
    
    if st.button("정책 확정 및 개별 화면 분석 시작"):
        st.session_state.common_policy_text = edited_policy
        st.session_state.step = AppStep.EXTRACT_FUNCTIONS.value
        st.rerun()

# --- Step 4: Extract Function Definitions ---
elif st.session_state.step == AppStep.EXTRACT_FUNCTIONS.value:
    st.subheader("화면별 기능 정의서 도출 및 검수")
    
    target_indices = [i for i, c in st.session_state.page_selections.items() if c == "분석 대상 화면"]
    total_targets = len(target_indices)
    
    if not st.session_state.function_definitions:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text(f"비동기 병렬 분석을 준비 중입니다... (대상 화면 {total_targets}장)")
        
        async def run_extractions() -> List[Dict[str, Any]]:
            sem = asyncio.Semaphore(5)
            
            async def bounded_extract(img_path: str, slide_num: int, policy: str) -> Dict[str, Any]:
                async with sem:
                    try:
                        return await async_extract_function_definition(img_path, slide_num, policy)
                    except Exception as e:
                        logger.error(f"Slide {slide_num} 분석 중 오류 발생", exc_info=True)
                        return {
                            "슬라이드_번호": slide_num,
                            "화면명": f"분석 오류 (Slide {slide_num})",
                            "화면_목적_추론": f"에러: {str(e)}",
                            "자가_점검_기록": "API 호출 또는 파싱 오류 발생",
                            "기능_목록": [
                                {
                                    "기능_식별자": f"S{slide_num}_ERROR",
                                    "상위_기능_식별자": "없음",
                                    "화면_영역": "오류",
                                    "기능명": "API 호출 실패 (재분석 필요)",
                                    "발생_조건": "없음",
                                    "사전_조건": "없음",
                                    "정상_처리_결과": "없음",
                                    "유효성_검증_및_예외_로직": "없음"
                                }
                            ]
                        }

            tasks = []
            for page_idx in target_indices:
                img_path = st.session_state.image_paths[page_idx]
                slide_number = page_idx + 1
                tasks.append(
                    bounded_extract(img_path, slide_number, st.session_state.common_policy_text)
                )
            
            completed = 0
            results = []
            for coro in asyncio.as_completed(tasks):
                res = await coro
                if isinstance(res, dict):
                    results.append(res)
                completed += 1
                progress_bar.progress(completed / total_targets)
                status_text.text(f"비동기 병렬 분석 중... 완료: {completed}/{total_targets}")
            return results
            
        results = asyncio.run(run_extractions())
        # 결과를 슬라이드 번호 순으로 정렬 (비동기는 완료 순서가 랜덤하므로)
        results.sort(key=lambda x: x.get('슬라이드_번호', 0))
        
        st.session_state.function_definitions = results
        st.rerun()
        
    # Render Data Editor
    # Flatten definitions for the editor
    flat_data = []
    for item in st.session_state.function_definitions:
        slide_num = item.get("슬라이드_번호", "")
        screen_name = item.get("화면명", "")
        for func in item.get("기능_목록", []):
            flat_item = {
                "슬라이드 번호": slide_num,
                "화면명": screen_name,
                "상위 기능 식별자": func.get("상위_기능_식별자", ""),
                "기능 식별자": func.get("기능_식별자", ""),
                "화면 영역": func.get("화면_영역", ""),
                "기능명": func.get("기능명", ""),
                "발생 조건": func.get("발생_조건", ""),
                "사전 조건": func.get("사전_조건", ""),
                "정상 처리 결과": func.get("정상_처리_결과", ""),
                "유효성 검증 및 예외 사항": func.get("유효성_검증_및_예외_로직", "")
            }
            flat_data.append(flat_item)
            
    df = pd.DataFrame(flat_data)
    
    # 1. LLM 중복 분석 실행 (최초 1회)
    if st.session_state.duplicate_clusters is None and flat_data:
        with st.spinner("AI가 기능 간의 의미론적 중복(Semantic Duplicates)을 분석하고 있습니다... (약 10~15초 소요)"):
            try:
                # 불필요한 토큰 낭비를 막기 위해 핵심 항목만 LLM에 전달
                llm_input_data = [
                    {
                        "기능_식별자": item["기능 식별자"],
                        "기능명": item["기능명"],
                        "화면_영역": item["화면 영역"],
                        "정상_처리_결과": item["정상 처리 결과"]
                    } for item in flat_data
                ]
                duplicate_res = find_semantic_duplicates(llm_input_data)
                st.session_state.duplicate_clusters = duplicate_res.get("중복_그룹_목록", [])
            except Exception as e:
                logger.error("중복 분석 중 오류 발생", exc_info=True)
                st.error(f"중복 분석 중 오류가 발생했습니다: {str(e)}")
                st.session_state.duplicate_clusters = []
        st.rerun()
    
    # 2. 색상 하이라이팅을 위한 매핑
    duplicate_id_map = {}
    if st.session_state.duplicate_clusters:
        for group in st.session_state.duplicate_clusters:
            for func_id in group.get("중복_기능_식별자_목록", []):
                duplicate_id_map[func_id] = True
    
    def highlight_dupes(row: pd.Series) -> List[str]:
        color = 'background-color: #ffe6e6' if duplicate_id_map.get(row['기능 식별자']) else ''
        return [color] * len(row)
        
    styled_df = df.style.apply(highlight_dupes, axis=1)
    
    with st.popover("❔ 표 편집기 사용 안내 (필독)"):
        st.markdown("""
        **기능 정의서 편집 가이드**  
        테스트 케이스는 체크 여부와 무관하게 표에 **최종적으로 남아있는 모든 내용**을 바탕으로 자동 생성됩니다.
        
        - **수정:** 잘못 추출된 내용은 표 안의 텍스트를 직접 클릭하여 수정하세요.
        - 🟥 **중복 표시:** 붉은색 배경은 서로 다른 화면에서 이름('기능명')이 중복 추출된 항목입니다. 둘 중 하나를 삭제하세요. (삭제된 항목에 속했던 하위 기능들은 살아남은 항목 아래로 자동 연결됩니다!)
        - **제외 (삭제):** 불필요한 기능은 해당 행(Row)의 맨 왼쪽 빈 공간을 클릭하여 선택한 후, 키보드의 `Delete` 키를 누르거나 우측 상단의 휴지통 아이콘을 눌러 지워주세요. (지워야만 테스트 케이스 생성에서 제외됩니다)
        - **추가:** 누락된 기능은 표 맨 아래의 빈칸에 직접 타이핑하여 새롭게 추가할 수 있습니다.
        """)
        
    edited_df = st.data_editor(styled_df, num_rows="dynamic", width="stretch")
    
    if st.button("위 확정 내용을 바탕으로 극단적 예외 상황 테스트 케이스 생성 시작"):
        # Auto-Reparenting Logic
        original_ids = set(df["기능 식별자"].astype(str).unique())
        edited_ids = set(edited_df["기능 식별자"].astype(str).unique())
        
        deleted_ids = original_ids - edited_ids
        
        for d_id in deleted_ids:
            if not d_id or d_id == "nan": continue
            
            # Find if this deleted ID was part of a duplicate cluster
            survivor_id = None
            if st.session_state.duplicate_clusters:
                for group in st.session_state.duplicate_clusters:
                    cluster_ids = group.get("중복_기능_식별자_목록", [])
                    if d_id in cluster_ids:
                        # Find a survivor ID from this cluster that is still in edited_df
                        for c_id in cluster_ids:
                            if c_id != d_id and c_id in edited_ids:
                                survivor_id = c_id
                                break
                    if survivor_id:
                        break
            
            if survivor_id:
                # Update children in edited_df that pointed to the deleted_id
                mask = edited_df["상위 기능 식별자"].astype(str) == d_id
                edited_df.loc[mask, "상위 기능 식별자"] = survivor_id
            else:
                # Fallback: Parent was deleted without a survivor
                mask = edited_df["상위 기능 식별자"].astype(str) == d_id
                edited_df.loc[mask, "상위 기능 식별자"] = "없음"
                
        # Re-construct JSON list from DF
        # We need to group by slide number
        grouped_data = {}
        for _, row in edited_df.iterrows():
            sn = row.get("슬라이드 번호")
            if sn not in grouped_data:
                grouped_data[sn] = {
                    "슬라이드_번호": sn,
                    "화면명": row.get("화면명"),
                    "기능_목록": []
                }
            grouped_data[sn]["기능_목록"].append({
                "상위_기능_식별자": row.get("상위 기능 식별자"),
                "기능_식별자": row.get("기능 식별자"),
                "화면_영역": row.get("화면 영역"),
                "기능명": row.get("기능명"),
                "발생_조건": row.get("발생 조건"),
                "사전_조건": row.get("사전 조건"),
                "정상_처리_결과": row.get("정상 처리 결과"),
                "유효성_검증_및_예외_로직": row.get("유효성 검증 및 예외 사항")
            })
        
        final_definitions = list(grouped_data.values())
        
        with st.spinner("테스트 케이스를 생성하는 중입니다..."):
            test_cases_result = generate_test_cases(final_definitions)
            st.session_state.test_cases_data = test_cases_result
            st.session_state.function_definitions = final_definitions # Save edited version
            st.session_state.step = AppStep.COMPLETE.value
            st.rerun()

# --- Step 5: Download ---
elif st.session_state.step == AppStep.COMPLETE.value:
    st.success("모든 분석 및 생성이 완료되었습니다.")
    
    # Generate Excels
    func_excel_path = os.path.join(st.session_state.session_dir, "기능정의서.xlsx")
    tc_excel_path = os.path.join(st.session_state.session_dir, "테스트케이스.xlsx")
    
    generate_function_definition_excel(st.session_state.function_definitions, func_excel_path)
    
    # Handle possible parsing failure of test cases
    if isinstance(st.session_state.test_cases_data, dict):
        generate_test_case_excel(st.session_state.test_cases_data, tc_excel_path)
    else:
        st.warning("테스트 케이스를 엑셀 형식으로 변환하는데 실패했습니다. 원본 텍스트를 저장합니다.")
        with open(tc_excel_path + ".txt", "w", encoding="utf-8") as f:
            f.write(str(st.session_state.test_cases_data))
        tc_excel_path = tc_excel_path + ".txt"

    col1, col2 = st.columns(2)
    with col1:
        with open(func_excel_path, "rb") as f:
            st.download_button("기능 정의서 엑셀 다운로드", data=f, file_name="기능정의서.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with col2:
        with open(tc_excel_path, "rb") as f:
            st.download_button("테스트 케이스 다운로드", data=f, file_name=os.path.basename(tc_excel_path))
