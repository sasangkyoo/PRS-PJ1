from pydantic import BaseModel, Field
from typing import List

class CommonPolicyList(BaseModel):
    프로젝트명: str
    공통_정책_목록: List[str]

class FunctionItem(BaseModel):
    기능_식별자: str = Field(description="'F_001', 'F_002'처럼 문서 내에서 고유한 일련번호 형식으로 기재")
    상위_기능_식별자: str = Field(description="이 기능이 속한 부모 기능의 식별자(예: F_001). 종속되지 않은 최상위 기능인 경우 '없음'")
    화면_영역: str
    기능명: str
    발생_조건: str
    사전_조건: str
    정상_처리_결과: str
    유효성_검증_및_예외_로직: str

class FunctionDefinitionData(BaseModel):
    슬라이드_번호: int
    화면명: str
    화면_목적_추론: str
    자가_점검_기록: str
    기능_목록: List[FunctionItem]

class TestCaseItem(BaseModel):
    슬라이드_번호: str = Field(description="원본 기능 정의서의 슬라이드 번호 그대로 복사")
    화면명: str = Field(description="원본 기능 정의서의 화면명 그대로 복사")
    테스트_식별자: str = Field(description="TC_화면명약자_001 형태의 고유 식별자 생성")
    참조_기능_식별자: str = Field(description="이 TC가 테스트하려는 대상 원본의 '기능_식별자'")
    테스트_유형: str = Field(description="'정상', '예외', '경계값' 중 택 1")
    테스트_목적: str = Field(description="무엇을 검증하기 위한 테스트인지 핵심만 요약")
    사전_조건: str = Field(description="테스트를 시작하기 전 시스템이 갖춰야 할 필수 상태")
    테스트_절차: str = Field(description="1. 입력창 클릭\n2. 'admin' 입력\n(사용자의 물리적 행동 순서대로 번호 매기기)")
    기대_결과: str = Field(description="화면에 노출되어야 할 정확한 알림 메시지나 상태 변화")

class TestCaseList(BaseModel):
    자가_점검_기록: str = Field(description="입력된 모든 기능_식별자에 대해 최소 1개 이상의 예외 TC가 생성되었는지 스스로 검증한 결과")
    테스트_케이스_목록: List[TestCaseItem]

class DuplicateGroup(BaseModel):
    기준_기능명: str = Field(description="중복된 기능들을 대표할 수 있는 공통 기능명")
    중복_기능_식별자_목록: List[str] = Field(description="서로 의미상 중복되는 기능_식별자들의 목록 (반드시 2개 이상이어야 함)")

class DuplicateList(BaseModel):
    중복_그룹_목록: List[DuplicateGroup]
