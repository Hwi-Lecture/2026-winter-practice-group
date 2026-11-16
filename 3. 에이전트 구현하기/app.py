import ast
import json
import operator
from pathlib import Path

import anthropic
import openpyxl
import streamlit as st

# 단계 목록: '다음 단계' 버튼을 누를 때마다 기능이 하나씩 켜짐
STAGES = [
    "0단계: 기본 챗봇",
    "1단계: 파일 첨부",
    "2단계: 대화 기억하기",
    "3단계: 계산기 도구",
    "4단계: 프로젝트 지침",
    "5단계: 지난 기록 기억하기",
    "6단계: 직접 파일 찾아 읽기",
]

# 단계별 설명: 추가된 기능 / 살펴볼 점 (/ 추가해 볼만한 기능)
GUIDES = [
    {
        "added": ["입력한 메시지 하나를 Claude API로 전송"],
        "check": [
            "'원본 보기'의 세 항목: `model`(사용할 모델), `max_tokens`(답변 최대 길이), `messages`(보낸 메시지)",
            "`messages`에는 방금 입력한 메시지 1개만 들어감",
            "채팅창에는 이전 대화가 남아 있지만, API로는 전송되지 않음",
        ],
    },
    {
        "added": [
            "입력창의 파일 첨부 버튼 (엑셀 파일)",
            "첨부한 엑셀의 모든 칸을 글로 바꿔서 메시지에 포함",
        ],
        "check": [
            "`content`가 [파일 내용, 질문] 두 덩어리로 나뉘어 전송됨",
            "엑셀 파일 자체가 아니라, 글로 바뀐 내용이 전달됨",
            "이전 대화를 보내지 않으므로, 질문할 때마다 파일을 다시 첨부해야 함",
            "참고: 파일이 큰 경우에는 전체 대신 필요한 부분만 골라 보내는 방식도 사용함",
        ],
    },
    {
        "added": ["지금까지 주고받은 대화 전체를 새 메시지와 함께 전송"],
        "check": [
            "`messages`에 `user`(내 메시지)와 `assistant`(Claude의 답)가 번갈아 쌓임",
            "한 번 첨부한 파일 내용도 질문할 때마다 다시 전송됨",
            "대화가 길어질수록 한 번에 보내는 양이 늘어남",
            "Claude가 대화를 기억하는 것이 아니라, 앱이 매번 대화 전체를 다시 보내는 방식",
        ],
    },
    {
        "added": [
            "계산기 도구: 요청에 `tools` 항목이 추가됨",
            "Claude가 계산기 사용을 요청하면, 앱(파이썬)이 계산한 뒤 결과를 돌려줌",
        ],
        "check": [
            "`tools`에 들어가는 내용: 도구 이름, 설명, 입력 형식",
            "질문 하나에 요청과 응답이 여러 번 오감 (요청 → 응답 → 요청 → …)",
            "응답의 `tool_use` 블록: 계산기 사용 요청 (Claude가 직접 계산하지 않음)",
            "다음 요청의 `tool_result` 블록: 앱이 계산한 결과",
            "도구가 없으면 계산을 모델이 직접 하고, 도구가 있으면 계산을 프로그램에 맡김",
        ],
    },
    {
        "added": [
            "프로젝트 지침: 요청에 `system` 항목이 추가됨",
            "분류 항목, 가맹점별 분류 규칙, 할부·취소 계산 규칙을 미리 전달",
        ],
        "check": [
            "'프로젝트 지침 보기'에서 지침 전문 확인",
            "지침은 매 요청마다 `messages`와 별도로 `system`에 담겨 전송됨",
            "'카카오페이 충전', '네이버페이'처럼 이름만으로는 용도를 알 수 없는 항목의 분류 결과",
            "할부 결제가 전체 금액이 아니라 매달 갚는 금액으로 계산되는지",
            "3단계(지침 없음)에서 같은 질문을 했을 때와 결과 비교",
        ],
    },
    {
        "added": [
            "기억 저장 도구: Claude가 기억할 내용을 직접 저장 요청함",
            "저장된 기억은 파일(`memory.md`)로 남고, 매 요청마다 지침 뒤에 붙어서 전송됨",
        ],
        "check": [
            "'저장된 기억 보기'에서 저장된 내용 확인",
            "'대화 지우기'를 눌러도 기억은 남아 있음 (대화 기록과의 차이)",
            "새로 저장한 기억은 다음 대화부터 전달됨 (대화를 시작할 때 기억을 한 번 불러옴)",
            "기억도 결국 매 요청에 함께 보내는 글: 요청 카드의 '시스템 프롬프트'에서 확인",
            "무엇을 기억할지는 Claude가 판단하고, 앱은 저장하고 붙여주기만 함",
            "시연 예: 9월 정리 → 대화 지우기 → 10월 파일로 \"9월보다 배달 많이 시켰어?\"",
        ],
    },
    {
        "added": [
            "파일 목록 보기, 파일 읽기 도구: `데이터` 폴더의 파일을 Claude가 직접 찾아서 읽음",
            "파일을 첨부하지 않아도 됨",
        ],
        "check": [
            "질문 하나에 Claude가 도구를 여러 번 이어서 사용함 (파일 목록 → 파일 읽기 → 계산기 → 기억 저장 …)",
            "새로 추가한 것은 도구 두 개뿐. 도구를 반복해서 쓰는 구조는 3단계부터 있었음",
            "지침 + 기억 + 도구 + 도구를 반복해서 쓰는 구조 = 에이전트",
            "시연 예: \"10월 가계부 정리하고 9월이랑 비교해 줘\"",
        ],
        "more": [
            "정리 결과를 엑셀 파일로 저장하는 도구",
            "항목별 지출을 그래프로 그리는 도구",
            "웹 검색 도구",
        ],
    },
]

MODEL = "claude-sonnet-5-5"
APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "데이터"  # [6단계] Claude가 직접 읽을 수 있는 폴더
MEMORY_FILE = APP_DIR / "memory.md"  # [5단계] 저장된 기억

# ---------- [4단계] 프로젝트 지침 (수강생은 보기만 가능) ----------
SYSTEM_PROMPT = """이 대화는 카드 이용내역으로 가계부를 정리하기 위한 것입니다.

## 분류 항목
식비, 배달, 카페, 편의점·간식, 장보기, 쇼핑, 생활용품, 교통, 주유, 통신, 구독, 운동, 의료, 문화, 모임비

## 가맹점 분류 규칙
- 쿠팡이츠, 우아한형제들(배민), 요기요: 배달
- 쿠팡: 쇼핑 / 쿠팡 와우멤버십: 구독
- 네이버페이: 쇼핑 (온라인 쇼핑 결제)
- 넷플릭스, 유튜브 프리미엄: 구독
- 후불교통 이용대금, 카카오T 택시: 교통
- GS칼텍스: 주유
- SK텔레콤 통신요금: 통신
- 수지스포츠짐: 운동
- 다이소: 생활용품
- 카카오페이 충전
  - 매달 1~5일에 충전하는 50,000원: 독서모임 회비 (모임비)
  - 그 외의 카카오페이 충전: 친구들과 식사 후 더치페이 정산 (식비)

## 계산 규칙
- 취소된 결제는 원래 결제와 서로 빼서 계산합니다.
- 할부 결제는 전체 금액이 아니라 매달 갚는 금액(결제 금액 ÷ 할부 개월 수)만 그달 지출로 계산합니다.
  예: 1,290,000원 3개월 할부 → 매달 430,000원
"""

st.set_page_config(page_title="단계별 챗봇", layout="wide")

if "stage" not in st.session_state:
    st.session_state.stage = 0
if "chat" not in st.session_state:
    st.session_state.chat = []  # 화면 표시용 (API에는 보내지 않음)
if "history" not in st.session_state:
    st.session_state.history = []  # [2단계] API에 보낼 수 있는 형태로 쌓아두는 대화 기록
if "exchange" not in st.session_state:
    st.session_state.exchange = []  # 마지막 질문 하나에 주고받은 요청과 응답 (순서대로)
if "turn_start" not in st.session_state:
    st.session_state.turn_start = 0  # 요청 안에서 '이번 질문'이 시작되는 위치 (그 앞은 이전 대화)
if "memory_snapshot" not in st.session_state:
    st.session_state.memory_snapshot = ""  # [5단계] 이번 대화를 시작할 때 불러온 기억


def clear_conversation():
    st.session_state.chat = []
    st.session_state.history = []
    st.session_state.exchange = []
    st.session_state.turn_start = 0


def change_stage(step):
    st.session_state.stage += step
    clear_conversation()


stage = st.session_state.stage

# ---------- 화면 꾸미기 ----------
st.html("""<style>
.block-container { padding-top: 2.5rem; }
/* 채팅창: 내 메시지는 오른쪽 */
.st-key-chat_box [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    flex-direction: row-reverse; margin-left: 25%; background: #EEF3FE;
}
.st-key-chat_box [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
    text-align: right;
}
/* 팝업: 요청/응답 카드를 가로로 나열 */
.st-key-flow { overflow-x: auto; flex-wrap: nowrap; padding-bottom: 0.5rem; }
.st-key-flow > div { flex-shrink: 0; }
.flow-arrow { font-size: 1.6rem; color: #9AA3B5; padding-top: 14rem; }
.card-title { font-weight: 700; font-size: 1.05rem; }
.card-sub { color: #6B7385; font-size: 0.85rem; margin-bottom: 0.3rem; }
.section { font-weight: 600; margin-top: 0.6rem; }
</style>""")

# ---------- 사이드바: API 키, 단계 목록 ----------
api_key = st.sidebar.text_input("API Key", type="password", placeholder="sk-ant-...")
st.sidebar.divider()
for i, name in enumerate(STAGES):
    st.sidebar.markdown(f"**▶ {name}**" if i == stage else f"<span style='color:gray'>{name}</span>",
                        unsafe_allow_html=True)
st.sidebar.divider()
st.sidebar.button("대화 지우기", on_click=clear_conversation, use_container_width=True)
st.sidebar.caption("단계를 바꾸면 대화가 새로 시작돼요.")

# ---------- 상단: 단계 이름, 이전/다음 단계 ----------
title_col, prev_col, next_col = st.columns([6, 1, 1], vertical_alignment="center")
title_col.subheader(STAGES[stage])
prev_col.button("이전 단계", on_click=change_stage, args=(-1,), disabled=stage == 0, use_container_width=True)
next_col.button("다음 단계", on_click=change_stage, args=(1,), disabled=stage == len(STAGES) - 1,
                use_container_width=True, type="primary")


# ---------- [1단계] 엑셀 파일을 글로 바꾸기 ----------
def excel_to_text(file):
    """엑셀의 모든 칸을 읽어서, 한 줄에 한 행씩 탭으로 구분한 글로 바꿈"""
    workbook = openpyxl.load_workbook(file, data_only=True)
    lines = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            if all(cell is None for cell in row):
                continue
            lines.append("\t".join("" if cell is None else str(cell) for cell in row).rstrip("\t"))
    return "\n".join(lines)


# ---------- [3단계] 계산기 도구 ----------
CALCULATOR_TOOL = {
    "name": "calculator",
    "description": "사칙연산 계산기. 숫자를 더하거나 빼는 등 계산이 필요할 때는 직접 계산하지 말고 이 도구를 사용하세요.",
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "계산할 수식. +, -, *, / 와 괄호 사용 가능. 예: (4400 + 66000) - 42900",
            }
        },
        "required": ["expression"],
    },
}

OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
             ast.USub: operator.neg, ast.UAdd: operator.pos}


def calculate(expression):
    """수식 문자열을 계산함. 숫자와 사칙연산 말고는 실행하지 않음"""
    def evaluate(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](evaluate(node.left), evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](evaluate(node.operand))
        raise ValueError("사칙연산만 계산할 수 있어요")

    result = evaluate(ast.parse(expression.replace(",", ""), mode="eval").body)
    return int(result) if float(result).is_integer() else result


# ---------- [5단계] 기억 저장 도구 ----------
MEMORY_TOOL = {
    "name": "save_memory",
    "description": "다음 대화에서도 알고 있어야 할 내용을 저장합니다. 월별 지출 정리 결과(항목별 합계 등)처럼 "
                   "나중에 비교하거나 다시 쓸 내용이 생기면 저장하세요. 저장된 기억은 다음 대화부터 지침과 함께 전달됩니다.",
    "input_schema": {
        "type": "object",
        "properties": {"content": {"type": "string", "description": "저장할 내용 (짧고 구체적으로)"}},
        "required": ["content"],
    },
}


def read_memory():
    return MEMORY_FILE.read_text(encoding="utf-8").strip() if MEMORY_FILE.exists() else ""


def save_memory(content):
    with MEMORY_FILE.open("a", encoding="utf-8") as f:
        f.write(f"- {content.strip()}\n")


def clear_memory():
    MEMORY_FILE.unlink(missing_ok=True)


# ---------- [6단계] 파일 목록 보기 / 파일 읽기 도구 ----------
LIST_FILES_TOOL = {
    "name": "list_files",
    "description": "데이터 폴더에 있는 파일 이름 목록을 봅니다.",
    "input_schema": {"type": "object", "properties": {}},
}

READ_FILE_TOOL = {
    "name": "read_file",
    "description": "데이터 폴더에 있는 엑셀 파일 하나를 읽어서 내용을 글로 돌려줍니다.",
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "읽을 파일 이름 (list_files로 확인한 이름)"}},
        "required": ["name"],
    },
}


def list_files():
    return sorted(p.name for p in DATA_DIR.glob("*.xlsx"))


def read_file(name):
    if name not in list_files():  # 데이터 폴더 밖의 파일은 읽지 않음
        raise ValueError(f"데이터 폴더에 '{name}' 파일이 없어요")
    return f"[파일: {name}]\n{excel_to_text(DATA_DIR / name)}"


# ---------- 도구 실행: Claude가 요청한 도구를 앱이 실행 ----------
def run_tool(name, tool_input):
    """도구를 실행하고 (Claude에게 돌려줄 결과, 채팅창에 보여줄 한 줄)을 돌려줌"""
    if name == "calculator":
        value = calculate(tool_input.get("expression", ""))
        return str(value), f"🧮 계산기: `{tool_input.get('expression', '')}` = **{value:,}**"
    if name == "save_memory":
        save_memory(tool_input.get("content", ""))
        return "저장했습니다.", f"🧠 기억 저장: {tool_input.get('content', '')}"
    if name == "list_files":
        names = list_files()
        return "\n".join(names) or "(파일 없음)", f"📂 파일 목록 보기: {len(names)}개"
    if name == "read_file":
        return read_file(tool_input.get("name", "")), f"📄 파일 읽기: {tool_input.get('name', '')}"
    raise ValueError(f"알 수 없는 도구: {name}")


def tools_for_stage():
    tools = []
    if stage >= 3:
        tools.append(CALCULATOR_TOOL)  # [3단계]
    if stage >= 5:
        tools.append(MEMORY_TOOL)  # [5단계]
    if stage >= 6:
        tools += [LIST_FILES_TOOL, READ_FILE_TOOL]  # [6단계]
    return tools


def system_for_stage():
    if stage < 4:
        return None
    system = SYSTEM_PROMPT  # [4단계]
    if stage >= 5:
        # [5단계] 대화를 시작할 때 불러온 기억을 지침 뒤에 붙임
        system += "\n## 저장된 기억\n" + (st.session_state.memory_snapshot or "(아직 없음)") + "\n"
    return system


# ---------- 채팅 ----------
chat_box = st.container(height=420, key="chat_box")
with chat_box:
    if not st.session_state.chat:
        st.caption("메시지를 입력하면 여기에 대화가 표시돼요.")
    for role, text in st.session_state.chat:
        st.chat_message(role).write(text)

with st.container():  # 컨테이너 안에 두면 입력창이 채팅창 바로 아래에 붙음
    if stage >= 1:
        # [1단계] 입력창에 파일 첨부 버튼이 생김
        submitted = st.chat_input("메시지를 입력하세요", accept_file="multiple", file_type=["xlsx"],
                                  key="input_1", disabled=not api_key)
        prompt = submitted.text if submitted else None
        files = submitted.files if submitted else []
    else:
        prompt = st.chat_input("메시지를 입력하세요", key="input_0", disabled=not api_key)
        files = []
    if not api_key:
        st.caption("왼쪽에 API 키를 입력하면 대화를 시작할 수 있어요.")

if prompt or files:
    client = anthropic.Anthropic(api_key=api_key)

    if files:
        # [1단계] 파일 내용을 글로 바꿔서, 질문과 함께 보냄
        content = [{"type": "text", "text": f"[첨부 파일: {f.name}]\n{excel_to_text(f)}"} for f in files]
        if prompt:
            content.append({"type": "text", "text": prompt})
        shown = "\n\n".join([f"📎 {f.name}" for f in files] + ([prompt] if prompt else []))
    else:
        content = prompt
        shown = prompt

    new_message = {"role": "user", "content": content}

    if stage >= 2:
        # [2단계] 지금까지의 대화 전체 + 새 메시지를 보냄
        messages = st.session_state.history + [new_message]
    else:
        # 이전 대화 없음: 지금 입력한 메시지 하나만 보냄
        messages = [new_message]

    if len(messages) == 1:
        # [5단계] 새 대화를 시작할 때 저장된 기억을 한 번 불러옴 (대화 중에는 바꾸지 않음)
        st.session_state.memory_snapshot = read_memory()

    st.session_state.exchange = []
    st.session_state.turn_start = len(messages) - 1
    tool_notes = []  # [3단계] 화면에 보여줄 도구 사용 기록

    with chat_box:
        st.chat_message("user").write(shown)
        with st.spinner("답변을 기다리는 중..."):
            while True:
                request = {"model": MODEL, "max_tokens": 16000}
                if system_for_stage():
                    request["system"] = system_for_stage()  # [4단계] 프로젝트 지침 (+ [5단계] 기억)
                request["messages"] = list(messages)
                if tools_for_stage():
                    request["tools"] = tools_for_stage()  # [3단계~] 사용할 수 있는 도구 목록

                response = client.messages.create(**request)
                st.session_state.exchange += [("request", request),
                                              ("response", response.model_dump(mode="json", exclude_none=True))]
                messages.append({
                    "role": "assistant",
                    "content": [b.model_dump(mode="json", exclude_none=True) for b in response.content],
                })

                if response.stop_reason != "tool_use":
                    break

                # [3단계] Claude가 도구 사용을 요청함 → 앱이 실행하고 결과를 돌려보냄
                results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    try:
                        result, note = run_tool(block.name, block.input)
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
                    except Exception as error:
                        results.append({"type": "tool_result", "tool_use_id": block.id,
                                        "content": f"오류: {error}", "is_error": True})
                        note = f"⚠️ {block.name} 오류: {error}"
                    tool_notes.append(note)
                messages.append({"role": "user", "content": results})

        answer = "".join(b.text for b in response.content if b.type == "text")
        shown_answer = "\n\n".join(tool_notes + [answer])
        st.chat_message("assistant").write(shown_answer)

    st.session_state.chat += [("user", shown), ("assistant", shown_answer)]
    # [2단계] 이번 질문과 답(도구 주고받은 내용 포함)을 대화 기록에 추가
    st.session_state.history = messages


# ---------- 팝업: API로 주고받은 내용 ----------
STOP_REASONS = {
    "end_turn": "답변 완료",
    "tool_use": "도구 사용 요청 → 앱이 도구를 실행한 뒤 다시 요청함",
    "max_tokens": "최대 길이(max_tokens)에 도달해서 멈춤",
    "refusal": "요청 거절",
}

TOOL_LABELS = {"calculator": "🧮 계산기", "save_memory": "🧠 기억 저장",
               "list_files": "📂 파일 목록 보기", "read_file": "📄 파일 읽기"}


def show_long_text(text, compact):
    """긴 글은 앞부분만 보여주고, 나머지는 펼쳐서 보게 함"""
    if text.startswith("[첨부 파일:") or text.startswith("[파일:"):
        first_line, _, body = text.partition("\n")
        label = f"📎 {first_line[1:-1]} ({len(body.splitlines())}줄)"
        if compact:
            st.caption(label)
        else:
            with st.expander(label):
                st.text(body)
    elif len(text) > 200:
        st.write(text[:200] + " …")
        if not compact:
            with st.expander("전체 보기"):
                st.write(text)
    else:
        st.write(text)


def show_block(block, compact=False):
    """메시지 안의 블록 하나를 읽기 쉬운 형태로 보여줌"""
    kind = block.get("type")
    if kind == "text":
        show_long_text(block["text"], compact)
    elif kind == "thinking":
        st.caption("💭 생각 블록 (내용은 숨겨져 있음)")
    elif kind == "tool_use":
        label = TOOL_LABELS.get(block["name"], block["name"])
        detail = ", ".join(str(v) for v in block["input"].values())
        st.markdown(f"**{label} 사용 요청**" + (f": `{detail}`" if detail else ""))
    elif kind == "tool_result":
        st.markdown("**도구 실행 결과**" + (" (오류)" if block.get("is_error") else ""))
        show_long_text(str(block["content"]), compact)
    else:
        st.caption(f"({kind} 블록)")


def show_message(message, compact=False):
    content = message["content"]
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
    if message["role"] == "assistant":
        name, avatar = "Claude", "assistant"
    elif all(b.get("type") == "tool_result" for b in blocks):
        name, avatar = "앱 (도구 실행 결과)", "🛠️"
    else:
        name, avatar = "나", "user"
    with st.chat_message(name, avatar=avatar):
        for block in blocks:
            show_block(block, compact)


def show_request(request, turn_start):
    st.markdown("<div class='section'>시스템 프롬프트</div>", unsafe_allow_html=True)
    if request.get("system"):
        with st.expander("펼쳐서 보기"):
            st.markdown(request["system"])
    else:
        st.caption("없음")

    st.markdown(f"<div class='section'>메시지 ({len(request['messages'])}개)</div>", unsafe_allow_html=True)
    earlier = request["messages"][:turn_start]
    if earlier:
        with st.expander(f"이전 대화 {len(earlier)}개 (요청할 때마다 다시 보냄)"):
            for message in earlier:
                show_message(message, compact=True)
    for message in request["messages"][turn_start:]:
        show_message(message)

    st.markdown("<div class='section'>도구 목록</div>", unsafe_allow_html=True)
    tools = request.get("tools", [])
    if not tools:
        st.caption("없음")
    for tool in tools:
        st.markdown(f"- `{tool['name']}`: {tool['description']}")


def show_response(response):
    st.markdown("<div class='section'>응답 내용</div>", unsafe_allow_html=True)
    show_message({"role": "assistant", "content": response["content"]})

    st.markdown("<div class='section'>멈춘 이유</div>", unsafe_allow_html=True)
    reason = response.get("stop_reason")
    st.caption(f"`{reason}`: {STOP_REASONS.get(reason, '')}")

    usage = response.get("usage", {})
    st.markdown("<div class='section'>사용량</div>", unsafe_allow_html=True)
    st.caption(f"입력 {usage.get('input_tokens', 0):,} 토큰 · 출력 {usage.get('output_tokens', 0):,} 토큰")


@st.dialog("API로 주고받은 내용", width="large")
def show_exchange():
    exchange = st.session_state.exchange
    st.caption(f"마지막 질문 하나에 앱과 Claude가 주고받은 순서예요. 요청 {len(exchange) // 2}번, 응답 {len(exchange) // 2}번.")
    with st.container(horizontal=True, gap="small", key="flow"):
        for i, (kind, data) in enumerate(exchange, start=1):
            if i > 1:
                st.markdown("<div class='flow-arrow'>→</div>", unsafe_allow_html=True)
            with st.container(border=True, width=380, height=560):
                if kind == "request":
                    st.markdown(f"<div class='card-title'>{i}. 요청</div><div class='card-sub'>앱 → Claude</div>",
                                unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='card-title'>{i}. 응답</div><div class='card-sub'>Claude → 앱</div>",
                                unsafe_allow_html=True)
                readable_tab, raw_tab = st.tabs(["메시지 보기", "원본 보기"])
                with readable_tab:
                    if kind == "request":
                        show_request(data, st.session_state.turn_start)
                    else:
                        show_response(data)
                with raw_tab:
                    st.code(json.dumps(data, ensure_ascii=False, indent=2), language="json")


# ---------- 팝업: [4단계] 프로젝트 지침 ----------
@st.dialog("프로젝트 지침", width="medium")
def show_instructions():
    st.caption("매 요청의 `system` 항목에 담겨 전송되는 내용이에요. 이 화면에서는 고칠 수 없어요.")
    with st.container(border=True):
        st.markdown(SYSTEM_PROMPT)


# ---------- 팝업: [5단계] 저장된 기억 ----------
@st.dialog("저장된 기억", width="medium")
def show_memory():
    st.caption(f"파일 위치: `{MEMORY_FILE.name}` · 대화를 시작할 때 불러와서, 매 요청마다 프로젝트 지침 뒤에 붙여 보내요. "
               "새로 저장한 기억은 다음 대화부터 전달돼요.")
    memory = read_memory()
    with st.container(border=True):
        st.markdown(memory or "아직 저장된 기억이 없어요.")
    if st.button("기억 지우기", disabled=not memory):
        clear_memory()
        st.rerun()


# ---------- 하단: 단계 설명, 팝업 버튼 ----------
with st.container(border=True):
    guide = GUIDES[stage]
    columns = st.columns(3 if "more" in guide else 2)
    columns[0].markdown("**추가된 기능**\n" + "\n".join(f"- {t}" for t in guide["added"]))
    columns[1].markdown("**살펴볼 점**\n" + "\n".join(f"- {t}" for t in guide["check"]))
    if "more" in guide:
        columns[2].markdown("**추가해 볼만한 기능**\n" + "\n".join(f"- {t}" for t in guide["more"]))

    with st.container(horizontal=True, horizontal_alignment="right"):
        if stage >= 4 and st.button("프로젝트 지침 보기"):
            show_instructions()
        if stage >= 5 and st.button("저장된 기억 보기"):
            show_memory()
        if st.button("API로 전송된 내용 보기", disabled=not st.session_state.exchange, type="primary"):
            show_exchange()
