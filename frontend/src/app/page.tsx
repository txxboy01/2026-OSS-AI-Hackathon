"use client";

import { useEffect, useRef, useState } from "react";

type SampleKey = "suncheon" | "login" | "app";
type UserAction = "NOT_INTERACTED" | "OPENED_LINK" | "SUBMITTED_CREDENTIALS" | "SUBMITTED_PERSONAL" | "SENT_MONEY" | "INSTALLED_APP";
type Evidence = { id: string; type: string; label: string; quote: string };
type AnalyzeResponse = { status: "VERIFIED" | "NO_ACTION_FOUND" | "FALLBACK"; evidence: Evidence[]; notice: string; limitation: string };
type GuidanceResponse = { urgency: "routine" | "prompt" | "urgent"; steps: { code: string; priority: number; title: string; body: string }[]; notice: string; limitation: string };

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const samples = {
  suncheon: { name: "지원금 사칭", text: `[순천시 지원금 신청 안내]
지원금 신청 대상자로 선정되었습니다.
본인 확인을 위해 인증번호를 알려주세요.
아래 주소에서 신청을 진행해 주세요.`, official: "https://www.suncheon.go.kr/kr/" },
  login: { name: "로그인 유도", text: `[계정 확인 안내]
오늘 안에 계정을 확인하지 않으면 이용이 제한됩니다.
아래 링크에서 로그인해 주세요.` },
  app: { name: "앱 설치 유도", text: `[배송 지연 안내]
오늘 안에 배송 정보를 확인하지 않으면 주문이 취소될 수 있습니다.
아래 링크에서 배송 확인 앱을 설치해 주세요.` },
} as const;
const actions: { value: UserAction; label: string }[] = [
  { value: "NOT_INTERACTED", label: "아직 누르지 않았어요" }, { value: "OPENED_LINK", label: "링크만 열었어요" },
  { value: "SUBMITTED_CREDENTIALS", label: "인증번호·비밀번호 입력" }, { value: "SUBMITTED_PERSONAL", label: "개인정보를 입력했어요" },
  { value: "SENT_MONEY", label: "송금·결제했어요" }, { value: "INSTALLED_APP", label: "앱을 설치했어요" },
];

function apiError(payload: unknown, fallback: string) {
  if (payload && typeof payload === "object" && "error" in payload) {
    const message = (payload as { error?: { message?: unknown } }).error?.message;
    if (typeof message === "string") return message;
  }
  return fallback;
}

export default function Home() {
  const [sample, setSample] = useState<SampleKey>("suncheon");
  const [message, setMessage] = useState<string>(samples.suncheon.text);
  const [consent, setConsent] = useState(false);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [analysisError, setAnalysisError] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [selectedAction, setSelectedAction] = useState<UserAction | null>(null);
  const [guidance, setGuidance] = useState<GuidanceResponse | null>(null);
  const [guidanceError, setGuidanceError] = useState("");
  const [isGuiding, setIsGuiding] = useState(false);
  const [modal, setModal] = useState<"about" | "privacy" | null>(null);

  const analysisVersion = useRef(0);
  const analysisPending = useRef(false);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (!modal) return;
    const dialog = dialogRef.current;
    const opener = document.activeElement;
    function containFocus(event: KeyboardEvent) {
      if (event.key !== "Tab") return;
      const controls = dialog?.querySelectorAll<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])");
      const first = controls?.[0];
      const last = controls?.[controls.length - 1];
      if (document.activeElement === (event.shiftKey ? first : last)) {
        event.preventDefault();
        (event.shiftKey ? last : first)?.focus();
      }
    }
    dialog?.addEventListener("keydown", containFocus);
    dialog?.showModal();
    return () => {
      dialog?.removeEventListener("keydown", containFocus);
      dialog?.close();
      if (opener instanceof HTMLElement) opener.focus();
    };
  }, [modal]);

  function reset() { analysisVersion.current++; setAnalysis(null); setAnalysisError(""); }
  function selectSample(key: SampleKey) { setSample(key); setMessage(samples[key].text); reset(); }

  async function runAnalysis() {
    if (analysisPending.current) return;
    const messageText = message.trim();
    if (!messageText) return setAnalysisError("확인할 메시지를 입력해 주세요.");
    if (!consent) return setAnalysisError("분석을 위해 외부 AI 전송 동의가 필요합니다.");
    reset(); setIsAnalyzing(true);
    analysisPending.current = true;
    const version = analysisVersion.current;
    try {
      const response = await fetch(`${API_BASE_URL}/analyze`, { method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store", body: JSON.stringify({ messageText, consentToExternalAi: true }) });
      if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("서버 연결 상태를 확인해 주세요.");
      const payload: unknown = await response.json();
      if (!response.ok) throw new Error(apiError(payload, "분석 요청을 처리하지 못했습니다."));
      if (version === analysisVersion.current) setAnalysis(payload as AnalyzeResponse);
    } catch (error) {
      if (version === analysisVersion.current) setAnalysisError(error instanceof Error ? error.message : "분석 요청을 처리하지 못했습니다.");
    } finally { analysisPending.current = false; setIsAnalyzing(false); }
  }

  async function getGuidance(action: UserAction) {
    setSelectedAction(action); setGuidance(null); setGuidanceError(""); setIsGuiding(true);
    try {
      const response = await fetch(`${API_BASE_URL}/guidance`, { method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store", body: JSON.stringify({ actions: [action] }) });
      if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("서버 연결 상태를 확인해 주세요.");
      const payload: unknown = await response.json();
      if (!response.ok) throw new Error(apiError(payload, "대응 안내를 불러오지 못했습니다."));
      setGuidance(payload as GuidanceResponse);
    } catch (error) { setGuidanceError(error instanceof Error ? error.message : "대응 안내를 불러오지 못했습니다."); }
    finally { setIsGuiding(false); }
  }

  return <main>
    <header className="header shell"><a className="brand" href="#top" aria-label="RPM 홈"><span>R</span><strong>RPM</strong></a><nav><button className="navText" onClick={() => setModal("about")}>서비스 소개</button><button className="navText" onClick={() => setModal("privacy")}>개인정보 원칙</button><a className="navCta" href="#analyze">메시지 분석 시작 <b>→</b></a></nav></header>
    <section className="hero" id="top"><div className="shell"><h1>의심 메시지,<br />먼저 확인하세요.</h1><p className="subhead">AI가 메시지 속 ‘요구’를 원문과 함께 보여드립니다.</p>
      <section className="analyzer" id="analyze">
        {!analysis ? <>
          <div className="panelHeading"><div><h2>메시지를 붙여넣어 확인하세요</h2><p>개인정보를 지운 메시지를 붙여넣거나 샘플로 체험하세요.</p></div></div>
          <label>빠른 체험</label><div className="samples">{(Object.keys(samples) as SampleKey[]).map((key) => <button key={key} onClick={() => selectSample(key)} className={sample === key ? "selected" : ""}>{samples[key].name}</button>)}</div>
          <label htmlFor="message">확인할 메시지를 붙여넣으세요</label><textarea id="message" value={message} onChange={(event) => { setMessage(event.target.value); reset(); }} />
          <div className="privacy"><b>입력 전 확인</b><span>비밀번호, 인증번호, 계좌번호, 주민번호, 이메일 주소, 전화번호는 입력하지 마세요.</span></div>
          <label className="consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /><span>분석을 위해 비식별 메시지를 외부 AI에 전송하는 것에 동의합니다.</span></label>
          <p className="storageNote"><i /> 입력·분석 결과는 저장하지 않습니다.</p>{analysisError && <p className="requestError" role="alert">{analysisError}</p>}
          <button className="primary" disabled={isAnalyzing} onClick={runAnalysis}>{isAnalyzing ? "AI 분석 중..." : "AI 분석 실행하기"} <b>→</b></button>
        </> : <>
          <div className="panelHeading resultHeading"><div><h2>AI 분석 결과</h2><p><strong>{analysis.status === "VERIFIED" ? "인용 근거 확인" : "분석 안내"}</strong> · {analysis.notice}</p></div><span className="limit">피싱 확정 아님</span></div>
          {analysis.status === "VERIFIED" ? <div className="evidenceGrid">{analysis.evidence.map((item) => <article className="evidence" key={item.id}><span className={item.type === "PRESSURE" ? "tag amber" : "tag"}>{item.label}</span><blockquote>“{item.quote}”</blockquote></article>)}</div> : <div className="emptyResult"><b>원문 근거를 표시하지 않습니다.</b><p>{analysis.notice}</p></div>}
          <div className="privacy"><b>분석의 한계</b><span>{analysis.limitation}</span></div>
        </>}
        <div className="buttons guideEntry"><button className={analysis ? "primary" : "secondary"} aria-expanded={showGuide} aria-controls="response" onClick={() => setShowGuide(true)}>내 상황에 맞는 대응 보기 <b>→</b></button>{analysis && <button className="secondary" onClick={reset}>새 메시지 분석</button>}</div>
          {showGuide && <section className="response" id="response"><h3>지금 어디까지 진행했나요?</h3><p>현재 행동을 고르면, 백엔드가 제공하는 다음 대응 순서를 보여드립니다.</p><div className="actions">{actions.map((item) => <button key={item.value} className={selectedAction === item.value ? "active" : ""} disabled={isGuiding} onClick={() => getGuidance(item.value)}>{item.label}</button>)}</div>{sample === "suncheon" && <a className="officialLink" href={samples.suncheon.official} target="_blank" rel="noreferrer"><span>공식 경로 확인</span>순천시 공식 홈페이지 열기 <b>↗</b></a>}{guidanceError && <p className="requestError" role="alert">{guidanceError}</p>}{guidance && <div className="plan"><b>{guidance.urgency === "urgent" ? "지금 우선 확인하세요." : "다음 순서를 확인하세요."}</b><ol>{guidance.steps.map((step) => <li key={step.code}><strong>{step.title}</strong><span>{step.body}</span></li>)}</ol><small>{guidance.notice} {guidance.limitation}</small></div>}</section>}
      </section>
      <section className="trust"><article><span>↗</span><h3>원문 근거 확인</h3><p>AI가 인용한 문장을 분석 원문에서 직접 확인합니다.</p></article><article><span>✓</span><h3>근거 없는 결과 차단</h3><p>원문에 없는 인용이나 금지 표현이 있으면 결과를 표시하지 않습니다.</p></article><article><span>⌁</span><h3>입력·결과 미저장</h3><p>현재 탭의 분석만 처리하며 새로고침하면 결과가 제거됩니다.</p></article></section>
    </div></section>
    <footer className="shell">RPM · 근거 검증형 AI 피싱 메시지 분석·대응 서비스</footer>
    {modal && <dialog ref={dialogRef} className="modalBackdrop" aria-label={modal === "about" ? "서비스 소개" : "개인정보 원칙"} onCancel={(event) => { event.preventDefault(); setModal(null); }} onClick={(event) => { if (event.target === event.currentTarget) setModal(null); }}><section className="modal"><button className="close" aria-label="닫기" onClick={() => setModal(null)}>×</button>{modal === "about" ? <><p className="eyebrow">HOW RPM WORKS</p><h2>판정이 아니라,<br />멈추고 확인할 근거를 보여줍니다.</h2><p className="modalLead">RPM은 실제 피싱이나 계정 침해를 확정하지 않습니다. 메시지가 요구하는 행동과 원문 근거를 보여주고, 사용자가 안전한 다음 행동을 선택하도록 돕습니다.</p><div className="modalSteps"><Step number="1" title="메시지 입력" text="안전 샘플 또는 비식별 처리한 메시지를 분석합니다." /><Step number="2" title="원문 근거 확인" text="AI 인용문을 원문과 비교합니다." /><Step number="3" title="상황별 대응" text="실제로 한 행동에 맞는 다음 순서를 확인합니다." /></div></> : <><p className="eyebrow">PRIVACY BY DESIGN</p><h2>입력은 최소화하고,<br />분석 결과는 저장하지 않습니다.</h2><p className="modalLead">실제 메시지를 분석할 때도 비밀번호, 인증번호, 계좌번호 등 민감정보를 지운 본문만 입력해야 합니다.</p><ul className="privacyList"><li>비밀번호·인증번호·계좌번호·주민번호는 입력하지 않습니다.</li><li>입력 메시지와 분석 결과를 브라우저 저장소에 보관하지 않습니다.</li><li>새로고침하거나 탭을 닫으면 현재 분석 결과가 사라집니다.</li><li>AI API 키는 프론트엔드에 노출하지 않고 백엔드에서 관리합니다.</li></ul></>}</section></dialog>}
  </main>;
}

function Step({ number, title, text }: { number: string; title: string; text: string }) { return <article className="step"><span>{number}</span><div><b>{title}</b><p>{text}</p></div></article>; }
