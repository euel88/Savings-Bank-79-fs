"""
Streamlit 기반 재무정보 추출기
GitHub Actions를 통해 배포 가능한 웹 애플리케이션
"""

import streamlit as st
import pandas as pd
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from fuzzywuzzy import fuzz
import logging
from datetime import datetime
import io
import base64
import openai
import os
import json

# 페이지 설정
st.set_page_config(
    page_title="재무정보 추출기",
    page_icon="💰",
    layout="wide"
)

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CSS 스타일 적용
st.markdown("""
<style>
    .main {
        padding: 0rem 1rem;
    }
    .stAlert {
        margin-top: 1rem;
    }
    h1 {
        color: #1f77b4;
    }
    .extraction-stat {
        font-size: 1.2rem;
        font-weight: bold;
        padding: 0.5rem;
        background-color: #f0f2f6;
        border-radius: 0.3rem;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

@dataclass
class AccountItem:
    """계정 항목 데이터 클래스"""
    id: int
    name: str
    aliases: List[str]
    category: str
    value: Optional[str] = None
    unit: Optional[str] = None
    source: Optional[str] = None
    note_ref: Optional[str] = None


class FinancialDataExtractor:
    """재무 데이터 추출기 - Streamlit 버전"""
    
    def __init__(self):
        self.account_items = self._initialize_account_items()
        self.extracted_data = {}
        
    def _initialize_account_items(self) -> Dict[int, AccountItem]:
        """75개 표준 계정 항목 초기화"""
        items = {
            # 기본 정보
            1: AccountItem(1, "날짜", ["기준일", "결산일", "보고서일"], "기본정보"),
            2: AccountItem(2, "은행명", ["금융기관명", "회사명", "법인명"], "기본정보"),
            
            # 재무상태표 항목
            3: AccountItem(3, "대출금", ["대출채권", "대출자산", "대출금잔액"], "재무상태표"),
            4: AccountItem(4, "예수금", ["예수부채", "고객예금", "예금"], "재무상태표"),
            5: AccountItem(5, "자기자본", ["자본총계", "총자본", "순자산"], "재무상태표"),
            14: AccountItem(14, "총자산", ["자산총계", "총자산", "자산합계"], "재무상태표"),
            15: AccountItem(15, "현금및예치금", ["현금및현금성자산", "현금예치금"], "재무상태표"),
            16: AccountItem(16, "유가증권", ["투자자산", "투자유가증권", "금융자산"], "재무상태표"),
            17: AccountItem(17, "대출금(상세)", ["대출채권", "대출금명세"], "재무상태표"),
            18: AccountItem(18, "대손충당금", ["대손충당부채", "신용손실충당금", "대출손실충당금"], "재무상태표"),
            19: AccountItem(19, "유형자산", ["유형자산", "고정자산", "설비자산"], "재무상태표"),
            20: AccountItem(20, "기타자산", ["기타자산", "기타유동자산", "기타비유동자산"], "재무상태표"),
            21: AccountItem(21, "예수금(상세)", ["예수금명세", "고객예금명세"], "재무상태표"),
            22: AccountItem(22, "자기자본(상세)", ["자본금", "자본잉여금", "이익잉여금"], "재무상태표"),
            
            # 손익계산서 항목
            6: AccountItem(6, "이자수익", ["이자수입", "대출이자수익", "이자소득"], "손익계산서"),
            7: AccountItem(7, "이자비용", ["이자비용", "예금이자비용", "차입이자"], "손익계산서"),
            9: AccountItem(9, "대손상각비", ["신용손실비용", "대손충당금전입액", "신용손실충당금전입액"], "손익계산서"),
            10: AccountItem(10, "당기순이익", ["당기순손익", "순이익", "당기총포괄이익"], "손익계산서"),
            24: AccountItem(24, "영업수익", ["영업수익", "총영업수익", "영업수익합계"], "손익계산서"),
            25: AccountItem(25, "이자수익(상세)", ["대출이자", "예금이자", "유가증권이자"], "손익계산서"),
            26: AccountItem(26, "유가증권 처분이익", ["유가증권처분이익", "매매이익", "투자자산처분이익"], "손익계산서"),
            27: AccountItem(27, "대출채권매각이익", ["대출채권매각이익", "매각이익"], "손익계산서"),
            28: AccountItem(28, "수수료수익", ["수수료수익", "수수료수입", "서비스수익"], "손익계산서"),
            29: AccountItem(29, "배당금수익", ["배당금수익", "배당수익", "투자배당금"], "손익계산서"),
            30: AccountItem(30, "기타영업수익", ["기타영업수익", "기타수익"], "손익계산서"),
            31: AccountItem(31, "영업비용", ["영업비용", "총영업비용", "영업비용합계"], "손익계산서"),
            32: AccountItem(32, "이자비용(상세)", ["예금이자", "차입금이자", "사채이자"], "손익계산서"),
            33: AccountItem(33, "유가증권 처분손실", ["유가증권처분손실", "매매손실", "투자자산처분손실"], "손익계산서"),
            34: AccountItem(34, "대출채권매각손실", ["대출채권매각손실", "매각손실"], "손익계산서"),
            35: AccountItem(35, "수수료비용", ["수수료비용", "지급수수료", "서비스비용"], "손익계산서"),
            36: AccountItem(36, "판관비", ["판매비와관리비", "판관비", "일반관리비"], "손익계산서"),
            37: AccountItem(37, "기타영업비용", ["기타영업비용", "기타비용"], "손익계산서"),
            38: AccountItem(38, "영업이익", ["영업이익", "영업손익", "영업이익(손실)"], "손익계산서"),
            39: AccountItem(39, "영업외수익", ["영업외수익", "기타수익", "특별이익"], "손익계산서"),
            40: AccountItem(40, "영업외비용", ["영업외비용", "기타비용", "특별손실"], "손익계산서"),
            41: AccountItem(41, "당기순이익(상세)", ["법인세차감전순이익", "법인세비용", "당기순이익"], "손익계산서"),
            
            # 유가증권 세부
            42: AccountItem(42, "유가증권 잔액", ["유가증권잔액", "투자자산잔액"], "유가증권"),
            43: AccountItem(43, "유가증권 수익", ["유가증권관련수익", "투자수익"], "유가증권"),
            44: AccountItem(44, "유가증권 이자수익", ["채권이자수익", "유가증권이자"], "유가증권"),
            45: AccountItem(45, "유가증권 처분이익(상세)", ["매매이익", "처분이익내역"], "유가증권"),
            46: AccountItem(46, "유가증권 배당금수익", ["주식배당금", "펀드배당금"], "유가증권"),
            47: AccountItem(47, "지분법평가이익", ["지분법이익", "관계기업투자이익"], "유가증권"),
            48: AccountItem(48, "유가증권 비용", ["유가증권관련비용", "투자비용"], "유가증권"),
            49: AccountItem(49, "유가증권 처분손실(상세)", ["매매손실", "처분손실내역"], "유가증권"),
            50: AccountItem(50, "유가증권 평가손실", ["평가손실", "미실현손실"], "유가증권"),
            51: AccountItem(51, "유가증권 손상차손", ["손상차손", "투자자산손상차손"], "유가증권"),
            52: AccountItem(52, "지분법평가손실", ["지분법손실", "관계기업투자손실"], "유가증권"),
            
            # 대출 및 충당금
            53: AccountItem(53, "충당금적립률", ["충당금적립률", "대손충당금비율"], "대출충당금"),
            54: AccountItem(54, "대출평잔", ["대출금평균잔액", "평균대출금"], "대출충당금"),
            55: AccountItem(55, "대출채권매각이익(A)", ["매각이익A", "대출매각수익"], "대출충당금"),
            56: AccountItem(56, "대출채권매각손실(B)", ["매각손실B", "대출매각비용"], "대출충당금"),
            57: AccountItem(57, "실질대손상각비(B-A)", ["순대손상각비", "실질대손비용"], "대출충당금"),
            
            # 경비 세부
            59: AccountItem(59, "경비 총계", ["판매비와관리비", "총경비", "영업경비"], "경비"),
            60: AccountItem(60, "광고선전비", ["광고비", "마케팅비용", "홍보비"], "경비"),
            61: AccountItem(61, "전산업무비", ["IT비용", "전산비", "시스템운영비"], "경비"),
            62: AccountItem(62, "용역비", ["아웃소싱비", "외주비", "용역수수료"], "경비"),
            63: AccountItem(63, "세금과공과", ["세금", "공과금", "조세공과"], "경비"),
            64: AccountItem(64, "임차료", ["임대료", "부동산임차료", "리스료"], "경비"),
            65: AccountItem(65, "감가상각비", ["유형자산감가상각비", "감가상각"], "경비"),
            66: AccountItem(66, "무형자산상각비", ["무형자산상각", "소프트웨어상각"], "경비"),
            67: AccountItem(67, "기타경비", ["기타판관비", "잡비"], "경비"),
            68: AccountItem(68, "대출금 평잔(억원)", ["대출평잔", "평균대출잔액"], "경비"),
            
            # 인건비
            71: AccountItem(71, "인건비 총계", ["인건비", "급여총액", "인건비합계"], "인건비"),
            72: AccountItem(72, "인건비", ["급여", "임금", "보수"], "인건비"),
            73: AccountItem(73, "복리후생비", ["복지비", "복리비", "후생비"], "인건비"),
            74: AccountItem(74, "평균 직원수", ["직원수", "종업원수", "임직원수"], "인건비"),
            75: AccountItem(75, "인당 인건비", ["1인당인건비", "평균인건비"], "인건비"),
            
            # 경영지표
            8: AccountItem(8, "예대마진율", ["예대마진", "NIM", "순이자마진"], "경영지표"),
            11: AccountItem(11, "BIS", ["BIS비율", "자기자본비율"], "경영지표"),
            12: AccountItem(12, "고정이하여신비율", ["고정이하비율", "부실여신비율"], "경영지표"),
            13: AccountItem(13, "연체율", ["연체율", "대출연체율"], "경영지표"),
            23: AccountItem(23, "BIS비율(상세)", ["기본자본비율", "보완자본비율"], "경영지표"),
            58: AccountItem(58, "대손상각비율", ["대손비율", "상각률"], "경영지표"),
            69: AccountItem(69, "대출금 평잔 比 경비율", ["경비율", "영업경비율"], "경영지표"),
            70: AccountItem(70, "대출금 평잔 比 광고비율", ["광고비율", "마케팅비율"], "경영지표"),
        }
        
        return items
    
    def extract_from_md(self, md_content: str) -> Dict:
        """MD 파일에서 데이터 추출"""
        logger.info("="*50)
        logger.info("MD 파일 분석 시작")
        logger.info(f"문서 크기: {len(md_content)} 문자")
        
        # 초기화
        self.extracted_data = {}
        
        # 진행 상태 표시
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 1. 문서 구조 파악
        status_text.text("📄 문서 구조 파악 중...")
        progress_bar.progress(0.1)
        sections = self._parse_document_structure(md_content)
        
        # 2. 재무제표 본문 추출
        status_text.text("💰 재무제표 본문 추출 중...")
        progress_bar.progress(0.3)
        self._extract_financial_statements(sections)
        
        # 3. 주석 추출 및 연계
        status_text.text("📝 주석 추출 및 연계 중...")
        progress_bar.progress(0.5)
        self._extract_and_link_notes(sections)
        
        # 4. 누락 항목 재탐색
        status_text.text("🔍 누락 항목 재탐색 중...")
        progress_bar.progress(0.7)
        self._search_missing_items(md_content)
        
        # 5. 계산 가능 항목 처리
        status_text.text("🧮 계산 가능 항목 처리 중...")
        progress_bar.progress(0.9)
        self._calculate_derived_items()
        
        # 완료
        status_text.text("✅ 추출 완료!")
        progress_bar.progress(1.0)
        
        return self.extracted_data
    
    def _parse_document_structure(self, content: str) -> Dict[str, str]:
        """문서 구조 파싱"""
        sections = {}
        
        # 주요 섹션 패턴
        patterns = {
            '재무상태표': [
                r'재\s*무\s*상\s*태\s*표',
                r'요\s*약\s*분\s*기\s*재\s*무\s*상\s*태\s*표',
                r'Statement\s+of\s+Financial\s+Position',
            ],
            '손익계산서': [
                r'손\s*익\s*계\s*산\s*서',
                r'요\s*약\s*분\s*기\s*손\s*익\s*계\s*산\s*서',
                r'Income\s+Statement',
            ],
            '주석': [
                r'주\s*석',
                r'주석\s*\d+',
                r'Notes?\s+to\s+Financial\s+Statements?',
            ],
        }
        
        # 섹션 찾기
        for section_name, pattern_list in patterns.items():
            for pattern in pattern_list:
                matches = list(re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE))
                if matches:
                    start = matches[0].start()
                    # 다음 섹션 찾기
                    next_section = len(content)
                    for other_section, other_patterns in patterns.items():
                        if other_section != section_name:
                            for other_pattern in other_patterns:
                                next_matches = list(re.finditer(other_pattern, content[start+100:], re.IGNORECASE))
                                if next_matches:
                                    next_section = min(next_section, start + 100 + next_matches[0].start())
                    
                    sections[section_name] = content[start:next_section]
                    break
        
        # 섹션을 찾지 못한 경우 전체 문서 사용
        if not sections:
            sections['전체문서'] = content
            
        return sections
    
    def _extract_financial_statements(self, sections: Dict[str, str]):
        """재무제표 본문에서 데이터 추출"""
        for section_name, content in sections.items():
            if '재무상태표' in section_name:
                self._extract_balance_sheet(content)
            elif '손익계산서' in section_name:
                self._extract_income_statement(content)
    
    def _extract_balance_sheet(self, content: str):
        """재무상태표 데이터 추출"""
        # MD 테이블 형식 처리
        if '|' in content:
            self._extract_from_md_table(content, "재무상태표")
        
        # 일반 텍스트 형식 처리
        self._extract_with_patterns(content, "재무상태표")
    
    def _extract_income_statement(self, content: str):
        """손익계산서 데이터 추출"""
        # MD 테이블 형식 처리
        if '|' in content:
            self._extract_from_md_table(content, "손익계산서")
        
        # 일반 텍스트 형식 처리
        self._extract_with_patterns(content, "손익계산서")
    
    def _extract_from_md_table(self, content: str, section_name: str):
        """MD 테이블에서 데이터 추출"""
        lines = content.split('\n')
        tables = []
        current_table = []
        in_table = False
        
        for line in lines:
            if '|' in line:
                if not re.match(r'^\s*\|[\s\-:]+\|', line):
                    cells = [cell.strip() for cell in re.split(r'\s*\|\s*', line)]
                    cells = [c for c in cells if c]
                    if cells:
                        current_table.append(cells)
                        in_table = True
                elif in_table and current_table:
                    tables.append(current_table)
                    current_table = []
            elif in_table and current_table:
                tables.append(current_table)
                current_table = []
                in_table = False
        
        if current_table:
            tables.append(current_table)
        
        # 각 테이블에서 데이터 추출
        for table in tables:
            for row in table:
                if len(row) >= 2:
                    self._match_account_in_row(row, section_name)
    
    def _extract_with_patterns(self, content: str, section_name: str):
        """패턴 매칭으로 데이터 추출"""
        patterns = [
            r'([가-힣\s\(\)]+)\s+([\d,]+)\s*(?:천원|백만원|억원)?',
            r'([가-힣\s\(\)]+)\s*[:：]\s*([\d,]+)',
            r'([가-힣\s\(\)]+)\s*(?:\(주\d+\))?\s*([\d,]+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                account_text = match[0].strip()
                value_text = match[1].strip()
                self._match_account(account_text, value_text, section_name)
    
    def _match_account_in_row(self, row: List[str], source: str):
        """테이블 행에서 계정 매칭"""
        account_name = row[0]
        
        for item_id, account in self.account_items.items():
            if item_id in self.extracted_data:
                continue
                
            for name in [account.name] + account.aliases:
                if self._is_similar(name, account_name):
                    for cell in row[1:]:
                        if re.search(r'[\d,]+', cell):
                            value = re.search(r'([\d,]+)', cell).group(1)
                            self.extracted_data[item_id] = {
                                'name': account.name,
                                'value': value,
                                'source': source
                            }
                            break
                    break
    
    def _match_account(self, account_text: str, value_text: str, source: str):
        """계정명과 값 매칭"""
        for item_id, account in self.account_items.items():
            if item_id in self.extracted_data:
                continue
                
            for name in [account.name] + account.aliases:
                if self._is_similar(name, account_text):
                    self.extracted_data[item_id] = {
                        'name': account.name,
                        'value': value_text,
                        'source': source
                    }
                    break
    
    def _is_similar(self, name1: str, name2: str) -> bool:
        """문자열 유사도 체크"""
        # 공백 제거
        norm1 = re.sub(r'\s+', '', name1)
        norm2 = re.sub(r'\s+', '', name2)
        
        # 완전 일치
        if norm1 == norm2:
            return True
        
        # 부분 문자열
        if norm1 in norm2 or norm2 in norm1:
            return True
        
        # Fuzzy 매칭
        return fuzz.ratio(name1, name2) >= 80
    
    def _extract_and_link_notes(self, sections: Dict[str, str]):
        """주석 추출 및 연계"""
        if '주석' in sections:
            # 주석 내용에서 추가 정보 추출
            self._extract_with_patterns(sections['주석'], '주석')
    
    def _search_missing_items(self, full_content: str):
        """누락된 항목 재탐색"""
        # 모든 가능한 계정 추출
        patterns = [
            r'([가-힣\s\(\)]+)\s*[:：]?\s*([\d,]+)\s*(?:천원|백만원|억원)?',
            r'\|\s*([가-힣\s\(\)]+)\s*\|\s*([\d,]+)',
        ]
        
        all_accounts = []
        for pattern in patterns:
            matches = re.findall(pattern, full_content, re.MULTILINE)
            all_accounts.extend(matches)
        
        # Fuzzy matching으로 누락 항목 찾기
        for item_id, account in self.account_items.items():
            if item_id in self.extracted_data:
                continue
                
            best_match = None
            best_score = 0
            
            for found_name, found_value in all_accounts:
                for name in [account.name] + account.aliases:
                    score = fuzz.ratio(name, found_name.strip())
                    if score > best_score and score >= 70:
                        best_score = score
                        best_match = (found_name, found_value)
            
            if best_match:
                self.extracted_data[item_id] = {
                    'name': account.name,
                    'value': best_match[1],
                    'matched_name': best_match[0],
                    'similarity': best_score,
                    'source': 'Fuzzy Matching'
                }
    
    def _calculate_derived_items(self):
        """계산 가능한 항목 처리"""
        # 예대마진율 계산
        if 6 in self.extracted_data and 7 in self.extracted_data:
            try:
                이자수익 = float(self.extracted_data[6]['value'].replace(',', ''))
                이자비용 = float(self.extracted_data[7]['value'].replace(',', ''))
                if 이자수익 > 0:
                    예대마진율 = (이자수익 - 이자비용) / 이자수익 * 100
                    self.extracted_data[8] = {
                        'name': '예대마진율',
                        'value': f"{예대마진율:.2f}",
                        'source': '계산값'
                    }
            except:
                pass
    
    def generate_report(self) -> pd.DataFrame:
        """최종 보고서 생성"""
        report_data = []
        
        for item_id in sorted(self.account_items.keys()):
            account = self.account_items[item_id]
            
            if item_id in self.extracted_data:
                data = self.extracted_data[item_id]
                report_data.append({
                    'ID': item_id,
                    '계정명': account.name,
                    '카테고리': account.category,
                    '값': data['value'],
                    '출처': data['source'],
                    '상태': '추출완료'
                })
            else:
                report_data.append({
                    'ID': item_id,
                    '계정명': account.name,
                    '카테고리': account.category,
                    '값': 'N/A',
                    '출처': '미발견',
                    '상태': 'N/A'
                })
        
        return pd.DataFrame(report_data)


# AI 추출 기능 (옵션)
class AIEnhancedExtractor:
    """OpenAI API를 활용한 추출 기능"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        openai.api_key = api_key
        
    def extract_with_ai(self, md_content: str, missing_items: List[Dict]) -> Dict:
        """AI를 활용한 누락 항목 추출"""
        if not self.api_key:
            return {}
            
        try:
            # 누락된 항목들만 추출 요청
            prompt = self._create_prompt(md_content[:3000], missing_items)
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "재무제표에서 계정 항목과 값을 정확히 추출하는 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            # 응답 파싱
            result = json.loads(response.choices[0].message.content)
            return result.get("extracted_items", {})
            
        except Exception as e:
            st.error(f"AI 추출 중 오류 발생: {str(e)}")
            return {}
    
    def _create_prompt(self, content: str, missing_items: List[Dict]) -> str:
        """AI 프롬프트 생성"""
        items_text = "\n".join([f"- ID {item['id']}: {item['name']}" for item in missing_items[:10]])
        
        return f"""
다음 재무제표에서 아래 항목들의 값을 찾아주세요:

{items_text}

문서:
{content}

JSON 형식으로 응답해주세요:
{{
    "extracted_items": {{
        "항목ID": {{"value": "값", "unit": "단위"}}
    }}
}}
"""


# Streamlit 메인 앱
def main():
    """Streamlit 메인 함수"""
    st.title("💰 재무정보 추출기")
    st.markdown("### MD 파일에서 저축은행 재무정보를 자동으로 추출합니다")
    
    # 사이드바 설정
    with st.sidebar:
        st.header("⚙️ 설정")
        
        # AI 기능 설정
        use_ai = st.checkbox("AI 추출 기능 사용", value=False)
        api_key = ""
        
        if use_ai:
            api_key = st.text_input("OpenAI API Key", type="password", 
                                   help="누락된 항목을 AI로 추출합니다")
            if api_key:
                st.success("✅ API Key 입력됨")
            else:
                st.warning("⚠️ API Key를 입력하세요")
        
        st.markdown("---")
        st.markdown("### 📊 추출 가능 항목")
        st.markdown("총 **75개** 표준 계정 항목")
        st.markdown("- 재무상태표: 11개")
        st.markdown("- 손익계산서: 18개")
        st.markdown("- 경영지표: 8개")
        st.markdown("- 기타: 38개")
    
    # 파일 업로드
    uploaded_file = st.file_uploader(
        "MD 파일을 선택하세요",
        type=['md'],
        help="PDF에서 변환된 MD 파일을 업로드하세요"
    )
    
    if uploaded_file is not None:
        # 파일 읽기
        md_content = uploaded_file.read().decode('utf-8')
        
        # 파일 정보 표시
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("파일명", uploaded_file.name)
        with col2:
            st.metric("파일 크기", f"{len(md_content):,} 문자")
        with col3:
            st.metric("예상 시간", "약 10초")
        
        # 추출 버튼
        if st.button("🚀 추출 시작", type="primary"):
            # 추출기 생성
            extractor = FinancialDataExtractor()
            
            # 추출 실행
            with st.spinner("추출 진행 중..."):
                extracted_data = extractor.extract_from_md(md_content)
                
                # AI 추출 (옵션)
                if use_ai and api_key:
                    # 누락 항목 확인
                    missing_items = []
                    for item_id, account in extractor.account_items.items():
                        if item_id not in extracted_data:
                            missing_items.append({
                                'id': item_id,
                                'name': account.name
                            })
                    
                    if missing_items:
                        st.info(f"🤖 AI로 {len(missing_items)}개 누락 항목 추출 시도...")
                        ai_extractor = AIEnhancedExtractor(api_key)
                        ai_results = ai_extractor.extract_with_ai(md_content, missing_items)
                        
                        # AI 결과 병합
                        for item_id, data in ai_results.items():
                            if int(item_id) not in extracted_data:
                                extracted_data[int(item_id)] = {
                                    'name': extractor.account_items[int(item_id)].name,
                                    'value': data['value'],
                                    'source': 'AI 추출'
                                }
            
            # 보고서 생성
            report = extractor.generate_report()
            
            # 결과 표시
            st.success("✅ 추출 완료!")
            
            # 통계 표시
            total_items = len(report)
            extracted_items = len(report[report['상태'] == '추출완료'])
            extraction_rate = (extracted_items / total_items) * 100
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("전체 항목", f"{total_items}개")
            with col2:
                st.metric("추출 성공", f"{extracted_items}개", 
                         delta=f"{extracted_items - (total_items - extracted_items)}")
            with col3:
                st.metric("추출률", f"{extraction_rate:.1f}%",
                         delta=f"{extraction_rate - 50:.1f}%")
            with col4:
                st.metric("N/A 항목", f"{total_items - extracted_items}개")
            
            # 카테고리별 통계
            st.markdown("### 📈 카테고리별 추출 현황")
            
            category_stats = report[report['상태'] == '추출완료'].groupby('카테고리').size()
            category_total = report.groupby('카테고리').size()
            
            category_df = pd.DataFrame({
                '추출': category_stats,
                '전체': category_total
            }).fillna(0)
            category_df['추출률'] = (category_df['추출'] / category_df['전체'] * 100).round(1)
            
            st.bar_chart(category_df[['추출', '전체']])
            
            # 결과 테이블
            st.markdown("### 📋 추출 결과")
            
            # 필터링 옵션
            col1, col2 = st.columns([1, 3])
            with col1:
                show_all = st.checkbox("모든 항목 표시", value=False)
            with col2:
                category_filter = st.multiselect(
                    "카테고리 필터",
                    options=report['카테고리'].unique(),
                    default=[]
                )
            
            # 데이터 필터링
            filtered_report = report.copy()
            if not show_all:
                filtered_report = filtered_report[filtered_report['상태'] == '추출완료']
            if category_filter:
                filtered_report = filtered_report[filtered_report['카테고리'].isin(category_filter)]
            
            # 테이블 표시
            st.dataframe(
                filtered_report,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "ID": st.column_config.NumberColumn("ID", width="small"),
                    "계정명": st.column_config.TextColumn("계정명", width="medium"),
                    "카테고리": st.column_config.TextColumn("카테고리", width="small"),
                    "값": st.column_config.TextColumn("값", width="medium"),
                    "출처": st.column_config.TextColumn("출처", width="small"),
                    "상태": st.column_config.TextColumn("상태", width="small")
                }
            )
            
            # 다운로드 옵션
            st.markdown("### 💾 결과 다운로드")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Excel 다운로드
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    report.to_excel(writer, index=False, sheet_name='추출결과')
                excel_buffer.seek(0)
                
                st.download_button(
                    label="📊 Excel 다운로드",
                    data=excel_buffer,
                    file_name=f"{uploaded_file.name.replace('.md', '')}_추출결과_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            with col2:
                # CSV 다운로드
                csv = report.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📄 CSV 다운로드",
                    data=csv,
                    file_name=f"{uploaded_file.name.replace('.md', '')}_추출결과_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            # 추출된 데이터 미리보기
            with st.expander("🔍 추출된 원본 데이터 보기"):
                st.json(extracted_data)


if __name__ == "__main__":
    main()
