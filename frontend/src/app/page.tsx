"use client";

import { useMemo, useState } from "react";

type SampleKey = "suncheon" | "login" | "app";
type ActionKey = "none" | "link" | "info" | "app";

const samples = {
  suncheon: {
    name: "지원금 사칭",
    text: `[순천시 지원금 신청 안내]
지원금 신청 대상자로 선정되었습니다.
본인 확인을 위해 인증번호를 알려주세요.
아래 주소에서 신청을 진행해 주세요.`,
    evidence: [
      ["개인정보·인증 요구", "본인 확인을 위해 인증번호를 알려주세요.", "메시지가 인증번호 전달을 요구합니다.", "blue"],
      ["링크 이동 요구", "아래 주소에서 신청을 진행해 주세요.", "메시지가 외부 주소에서 신청 행동을 요구합니다.", "blue"],
      ["긴급성·혜택 강조", "지원금 신청 대상자로 선정되었습니다.", "지원금 대상자라는 혜택을 제시해 행동을 유도합니다.", "amber"],
    ],
    official: "https://www.suncheon.go.kr/kr/",
  },
  login: {
    name: "로그인 유도",
    text: `[계정 확인 안내]
오늘 안에 계정을 확인하지 않으면 이용이 제한됩니다.
아래 링크에서 로그인해 주세요.`,
    evidence: [
      ["로그인 요구", "아래 링크에서 로그인해 주세요.", "메시지가 외부 페이지에서 로그인 행동을 요구합니다.", "blue"],
      ["링크 이동 요구", "아래 링크에서 로그인해 주세요.", "메시지가 링크 이동을 요구합니다.", "blue"],
      ["긴급성 강조", "오늘 안에 계정을 확인하지 않으면 이용이 제한됩니다.", "즉시 행동하지 않으면 불이익이 있다고 강조합니다.", "amber"],
    ],
  },
  app: {
    name: "앱 설치 유도",
    text: `[배송 지연 안내]
오늘 안에 배송 정보를 확인하지 않으면 주문이 취소될 수 있습니다.
아래 링크에서 배송 확인 앱을 설치해 주세요.`,
    evidence: [
      ["앱 설치 요구", "배송 확인 앱을 설치해 주세요.", "메시지가 앱 설치라는 행동을 요구합니다.", "blue"],
      ["링크 이동 요구", "아래 링크에서 배송 확인 앱을 설치해 주세요.", "메시지가 외부 페이지로 이동하도록 요구합니다.", "blue"],
      ["긴급성 강조", "오늘 안에 배송 정보를 확인하지 않으면 주문이 취소될 수 있습니다.", "즉시 행동하지 않으면 불이익이 있다고 강조합니다.", "amber"],
    ],
  },
} as const;

const plans: Record<ActionKey, { title: string; steps: string[] }> = {
  none: { title: "지금은 누르지 않고 공식 경로에서 확인하세요.", steps: ["메시지 속 링크를 누르지 말고, 해당 기관의 공식 홈페이지나 대표번호로 안내를 확인하세요.", "인증번호·계좌 정보·비밀번호는 전달하지 마세요.", "의심 메시지는 삭제하고 필요하면 해당 기관에 신고하세요."] },
  link: { title: "열어 본 페이지에서는 아무것도 입력하지 마세요.", steps: ["열어 둔 페이지를 닫고, 파일을 내려받거나 권한을 허용하지 마세요.", "메시지 속 주소 대신 직접 검색한 공식 홈페이지에서 안내를 다시 확인하세요.", "로그인이나 정보를 입력했다면 ‘정보를 입력했어요’를 선택하세요."] },
  info: { title: "정보를 전달했다면 즉시 공식 채널에 연락하세요.", steps: ["의심 상대와 연락을 종료하세요.", "금융정보 또는 인증번호를 전달했다면 이용 중인 금융기관 공식 고객센터에 즉시 연락하세요.", "본인 모르게 출금·결제가 발생했다면 112 신고를 고려하세요."] },
  app: { title: "설치한 앱은 추가 권한을 주지 말고 점검하세요.", steps: ["앱을 실행하지 말고 접근성·알림·기기 관리자 권한을 확인하세요.", "출처가 불분명한 앱은 삭제하고 공식 고객센터에 점검 방법을 문의하세요.", "금융정보를 입력했거나 이상 거래가 있으면 금융기관에 즉시 연락하세요."] },
};

export default function Home() {
  const [sample, setSample] = useState<SampleKey>("suncheon");
  const [message, setMessage] = useState<string>(samples.suncheon.text);
  const [analyzed, setAnalyzed] = useState(false);
  const [action, setAction] = useState<ActionKey | null>(null);
  const [showGuide, setShowGuide] = useState(false);
  const [modal, setModal] = useState<"about" | "privacy" | null>(null);
  const active = samples[sample];
  const currentEvidence = useMemo(() => active.evidence, [active]);

  function selectSample(key: SampleKey) {
    setSample(key);
    setMessage(samples[key].text);
    setAnalyzed(false);
    setAction(null);
    setShowGuide(false);
  }

  return (
    <main>
      <header className="header shell">
        <a className="brand" href="#top" aria-label="RPM 홈"><span>R</span><strong>RPM</strong></a>
        <nav>
          <button className="navText" onClick={() => setModal("about")}>서비스 소개</button>
          <button className="navText" onClick={() => setModal("privacy")}>개인정보 원칙</button>
          <a className="navCta" href="#analyze">메시지 분석 시작 <b>→</b></a>
        </nav>
      </header>

      <section className="hero" id="top">
        <div className="shell">
          <h1>의심 메시지,<br />먼저 확인하세요.</h1>
          <p className="subhead">AI가 메시지 속 ‘요구’를 원문과 함께 보여드립니다.</p>

          <section className="analyzer" id="analyze">
            {!analyzed ? (
              <>
                <div className="panelHeading">
                  <div><h2>메시지를 붙여넣어 확인하세요</h2><p>개인정보를 지운 메시지를 붙여넣거나 샘플로 체험하세요.</p></div>
                </div>
                <label>빠른 체험</label>
                <div className="samples">
                  {(Object.keys(samples) as SampleKey[]).map((key) => <button key={key} onClick={() => selectSample(key)} className={sample === key ? "selected" : ""}>{samples[key].name}</button>)}
                </div>
                <label htmlFor="message">확인할 메시지를 붙여넣으세요</label>
                <textarea id="message" value={message} onChange={(e) => setMessage(e.target.value)} />
                <div className="privacy"><b>입력 전 확인</b><span>비밀번호, 인증번호, 계좌번호, 주민번호, 이메일 주소, 전화번호는 입력하지 마세요.</span></div>
                <p className="storageNote"><i /> 입력·분석 결과는 저장하지 않습니다.</p>
                <button className="primary" onClick={() => { setAnalyzed(true); setAction(null); setShowGuide(false); }}>AI 분석 실행하기 <b>→</b></button>
              </>
            ) : (
              <>
                <div className="panelHeading resultHeading">
                  <div><h2>AI 분석 결과</h2><p><strong>인용 근거 확인</strong> · AI 인용문이 입력한 메시지에 있습니다.</p></div>
                  <span className="limit">피싱 확정 아님</span>
                </div>
                <div className="evidenceGrid">
                  {currentEvidence.map(([label, quote, , tone]) => (
                    <article className="evidence" key={`${label}-${quote}`}>
                      <span className={tone === "amber" ? "tag amber" : "tag"}>{label}</span>
                      <blockquote>“{message.includes(quote) ? quote : "원문 인용 검증 실패"}”</blockquote>
                    </article>
                  ))}
                </div>
                <div className="privacy"><b>분석의 한계</b><span>이 결과만으로 피싱 또는 실제 침해 여부를 확정할 수 없습니다.</span></div>
                <div className="buttons"><button className="primary" onClick={() => setShowGuide(true)}>내 상황에 맞는 대응 보기 <b>→</b></button><button className="secondary" onClick={() => { setAnalyzed(false); setAction(null); setShowGuide(false); }}>새 메시지 분석</button></div>

                {showGuide && <section className="response" id="response">
                  <h3>지금 어디까지 진행했나요?</h3>
                  <p>현재 행동을 고르면, 이 메시지에서 멈추기 위한 다음 순서를 바로 보여드립니다.</p>
                  <div className="actions">
                    {(["none", "link", "info", "app"] as ActionKey[]).map((key) => <button key={key} className={action === key ? "active" : ""} onClick={() => setAction(key)}>{{ none: "아직 누르지 않았어요", link: "링크만 열었어요", info: "인증번호·정보를 입력했어요", app: "앱을 설치했어요" }[key]}</button>)}
                  </div>
                  {sample === "suncheon" && <a className="officialLink" href={samples.suncheon.official} target="_blank" rel="noreferrer"><span>공식 경로 확인</span>순천시 공식 홈페이지 열기 <b>↗</b></a>}
                  {action && <div className="plan"><b>{plans[action].title}</b><ol>{plans[action].steps.map((step) => <li key={step}>{step}</li>)}</ol><small>RPM은 이 메시지가 피싱이라고 확정하지 않습니다. 메시지에 나온 행동을 멈추고 공식 경로에서 확인하도록 돕습니다.</small></div>}
                </section>}
              </>
            )}
          </section>

          <section className="trust">
            <article><span>↗</span><h3>원문 근거 확인</h3><p>AI가 인용한 문장을 분석 원문에서 직접 확인합니다.</p></article>
            <article><span>✓</span><h3>근거 없는 결과 차단</h3><p>원문에 없는 인용이나 금지 표현이 있으면 결과를 표시하지 않습니다.</p></article>
            <article><span>⌁</span><h3>입력·결과 미저장</h3><p>현재 탭의 분석만 처리하며 새로고침하면 결과가 제거됩니다.</p></article>
          </section>
        </div>
      </section>

      <footer className="shell">RPM · 근거 검증형 AI 피싱 메시지 분석·대응 서비스</footer>

      {modal && <div className="modalBackdrop" role="presentation" onClick={() => setModal(null)}>
        <section className="modal" role="dialog" aria-modal="true" aria-label={modal === "about" ? "서비스 소개" : "개인정보 원칙"} onClick={(event) => event.stopPropagation()}>
          <button className="close" aria-label="닫기" onClick={() => setModal(null)}>×</button>
          {modal === "about" ? <>
            <p className="eyebrow">HOW RPM WORKS</p>
            <h2>판정이 아니라,<br />멈추고 확인할 근거를 보여줍니다.</h2>
            <p className="modalLead">RPM은 실제 피싱이나 계정 침해를 확정하지 않습니다. 메시지가 요구하는 행동과 원문 근거를 보여주고, 사용자가 안전한 다음 행동을 선택하도록 돕습니다.</p>
            <div className="modalSteps"><Step number="1" title="메시지 입력" text="안전 샘플 또는 비식별 처리한 메시지를 분석합니다." /><Step number="2" title="원문 근거 확인" text="로그인·송금·앱 설치·긴급성 요구를 원문과 비교합니다." /><Step number="3" title="상황별 대응" text="링크 열람·정보 입력 여부에 맞는 다음 행동을 확인합니다." /></div>
          </> : <>
            <p className="eyebrow">PRIVACY BY DESIGN</p>
            <h2>입력은 최소화하고,<br />분석 결과는 저장하지 않습니다.</h2>
            <p className="modalLead">실제 메시지를 분석할 때도 비밀번호, 인증번호, 계좌번호 등 민감정보를 지운 본문만 입력해야 합니다.</p>
            <ul className="privacyList"><li>비밀번호·인증번호·계좌번호·주민번호는 입력하지 않습니다.</li><li>입력 메시지와 분석 결과를 브라우저 저장소에 보관하지 않습니다.</li><li>새로고침하거나 탭을 닫으면 현재 분석 결과가 사라집니다.</li><li>AI API 키는 프론트엔드에 노출하지 않고 백엔드에서 관리합니다.</li></ul>
          </>}
        </section>
      </div>}
    </main>
  );
}

function Step({ number, title, text }: { number: string; title: string; text: string }) {
  return <article className="step"><span>{number}</span><div><b>{title}</b><p>{text}</p></div></article>;
}
