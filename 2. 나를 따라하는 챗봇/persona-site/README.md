# 나를 닮은 챗봇 · Sites 버전

수강생의 대화에서 말투와 성격 메모리를 만들고, 그 메모리를 다른 수강생에게 배정해 페르소나 챗봇과 대화하는 수업용 웹앱입니다.

## 폴더 구성

- `public/`: 수강생 화면과 관리자 화면의 원본 HTML
- `lib/prompts.js`: Claude 시스템 프롬프트와 메모리 도구 정의
- `worker/runtime.js`: Sites Worker API, R2 저장소, Claude 호출
- `worker/index.js`: 원본 HTML과 프롬프트를 합쳐 만든 Worker 파일. 직접 수정하지 말고 `runtime.js`, `public/`, `lib/prompts.js`를 수정합니다.
- `scripts/build-worker.mjs`: 원본 화면과 프롬프트를 Worker에 포함
- `scripts/build-site.mjs`: `dist/server/index.js`와 배포 manifest 생성
- `.openai/hosting.json`: Sites 프로젝트 ID와 R2 `BUCKET` 연결

Vercel 전용 API 라우트와 Blob 의존성은 제거했습니다. 수업 데이터는 R2에 저장되고, Anthropic API 키는 브라우저에 전달되지 않습니다.

## 빌드

Node.js 22 이상에서 실행합니다. 외부 패키지는 필요 없습니다.

```sh
npm run build
npm run validate
```

## 런타임 비밀 변수

Sites 프로젝트의 환경 변수에 다음 값을 비밀로 등록합니다.

- `ANTHROPIC_API_KEY`: 서버에서 사용할 Anthropic API 키
- `ADMIN_PASSWORD`: `/admin.html` 관리자 화면 비밀번호

## 수업 진행

1. 수강생에게 사이트 주소와 수업 코드(영문 소문자·숫자·`-`·`_`, 2~30자)를 안내합니다.
2. `/admin.html`에서 수업 코드와 관리자 비밀번호로 접속해 제출 현황을 보고 메모리를 배분합니다.
3. 수업이 끝나면 관리자 화면에서 해당 수업 데이터를 삭제합니다.
