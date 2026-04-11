import { useEffect, useState } from "react";

const METRIC_EXPLANATIONS = {
  margin: {
    title: "득점마진",
    body: "해당 팀 득점에서 상대 팀 득점을 뺀 값입니다. 양수면 앞섰고, 음수면 밀린 경기였습니다.",
  },
  off_rating: {
    title: "오펜시브 레이팅",
    body: "100번의 공격 기회당 몇 점을 냈는지 나타냅니다. 값이 높을수록 공격 효율이 좋습니다.",
  },
  def_rating: {
    title: "디펜시브 레이팅",
    body: "상대가 100번의 공격 기회에서 몇 점을 냈는지 나타냅니다. 값이 낮을수록 수비 효율이 좋습니다.",
  },
  net_rating: {
    title: "넷 레이팅",
    body: "오펜시브 레이팅에서 디펜시브 레이팅을 뺀 값입니다. 양수면 전체 경기력 우위, 음수면 열세를 뜻합니다.",
  },
  ast_to_ratio: {
    title: "AST/TO",
    body: "어시스트를 턴오버로 나눈 값입니다. 높을수록 실수 대비 패스 전개가 안정적이라는 뜻입니다.",
  },
  efg_pct: {
    title: "eFG%",
    body: "3점슛 가치를 반영한 실질 야투율입니다. 일반 야투율보다 슈팅 효율을 더 잘 보여줍니다.",
  },
  ts_pct: {
    title: "TS%",
    body: "2점, 3점, 자유투를 모두 포함한 종합 득점 효율입니다. 득점 생산성을 넓게 볼 때 유용합니다.",
  },
  rebound_rate: {
    title: "REB%",
    body: "전체 리바운드 중 이 팀이 가져온 비율입니다. 높을수록 볼 소유권 확보가 좋았다는 의미입니다.",
  },
  oreb_dreb_rate: {
    title: "OREB% / DREB%",
    body: "공격 리바운드 점유율과 수비 리바운드 점유율입니다. 세컨드 찬스와 수비 마무리 능력을 함께 보여줍니다.",
  },
  fg3_pct: {
    title: "3P%",
    body: "3점슛 성공률입니다. 외곽 효율이 얼마나 좋았는지 보여줍니다.",
  },
  turnover: {
    title: "턴오버",
    body: "공격권을 상대에게 넘겨준 횟수입니다. 값이 낮을수록 경기 운영이 안정적입니다.",
  },
};

export default function MetricInfoChip({ metricKey, label, value }) {
  const [open, setOpen] = useState(false);
  const info = METRIC_EXPLANATIONS[metricKey];

  useEffect(() => {
    if (!open) return;
    const onEsc = (event) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [open]);

  if (!info) {
    return (
      <div className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-left">
        <p className="text-[11px] font-semibold text-slate-500">{label}</p>
        <p className="mt-0.5 text-sm font-bold text-slate-800">{value}</p>
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-left transition-colors hover:bg-slate-50"
        onClick={() => setOpen(true)}
      >
        <p className="text-[11px] font-semibold text-slate-500">{label}</p>
        <div className="mt-0.5 flex items-center justify-between gap-2">
          <p className="text-sm font-bold text-slate-800">{value}</p>
          <span className="text-[11px] font-semibold text-blue-600">설명</span>
        </div>
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-bold text-slate-900">{info.title}</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">{info.body}</p>
              </div>
              <button
                type="button"
                className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                onClick={() => setOpen(false)}
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}