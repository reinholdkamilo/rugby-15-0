import type { CSSProperties, ReactNode } from "react";

export function RugbyField({ children }: { children: ReactNode }) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-cyan-300/20 bg-[#020713] p-4 shadow-[0_24px_80px_rgba(0,0,0,0.5)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_9%_12%,rgba(0,170,255,0.42),transparent_7%),radial-gradient(circle_at_18%_24%,rgba(0,132,255,0.34),transparent_11%),radial-gradient(circle_at_13%_39%,rgba(0,150,255,0.28),transparent_13%),radial-gradient(circle_at_25%_53%,rgba(0,74,190,0.2),transparent_17%),linear-gradient(135deg,rgba(255,255,255,0.026)_0_1px,transparent_1px_20px)]" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-[48%] opacity-20 bg-[linear-gradient(135deg,transparent_0_36%,rgba(36,116,230,0.34)_36%_44%,transparent_44%_56%,rgba(36,116,230,0.24)_56%_64%,transparent_64%)] bg-[length:92px_92px]" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_38%,rgba(0,0,0,0.78)_100%)]" />
      <div className="pointer-events-none absolute inset-x-10 top-28 bottom-8 rounded-full bg-cyan-400/16 blur-3xl" />

      <div className="pointer-events-none absolute inset-x-6 top-8 bottom-4 [perspective:980px]">
        <div className="absolute inset-x-0 top-[18%] bottom-1 overflow-hidden bg-[#061429]/54 shadow-[0_0_36px_rgba(0,166,255,0.6),0_0_96px_rgba(0,95,255,0.25),inset_0_0_34px_rgba(34,211,238,0.08)] [clip-path:polygon(20%_0,80%_0,100%_100%,0_100%)] [transform:rotateX(5deg)] [transform-origin:center_bottom]">
          <div className="absolute inset-0 border-2 border-cyan-300/90 shadow-[0_0_20px_rgba(0,179,255,0.85),inset_0_0_20px_rgba(0,179,255,0.18)] [clip-path:polygon(20%_0,80%_0,100%_100%,0_100%)]" />
          <div className="absolute inset-0 bg-[linear-gradient(135deg,rgba(255,255,255,0.026)_0_1px,transparent_1px_24px)]" />
          <FieldLine style={{ top: "9%" }} strength="soft" />
          <FieldLine style={{ top: "25%" }} strength="medium" />
          <FieldLine style={{ top: "38%" }} dashed />
          <FieldLine style={{ top: "50%" }} strength="strong" />
          <FieldLine style={{ bottom: "38%" }} dashed />
          <FieldLine style={{ bottom: "25%" }} strength="medium" />
          <FieldLine style={{ bottom: "9%" }} strength="soft" />
          <DashedGuide side="left" />
          <DashedGuide side="right" />
          <FieldLabel side="left" style={{ top: "25%" }} text="22" />
          <FieldLabel side="left" style={{ top: "38%" }} text="10" />
          <FieldLabel side="left" style={{ bottom: "38%" }} text="10" />
          <FieldLabel side="left" style={{ bottom: "25%" }} text="22" />
          <FieldLabel side="right" style={{ top: "25%" }} text="22" />
          <FieldLabel side="right" style={{ top: "38%" }} text="10" />
          <FieldLabel side="right" style={{ bottom: "38%" }} text="10" />
          <FieldLabel side="right" style={{ bottom: "25%" }} text="22" />
          <div className="absolute left-1/2 top-1/2 h-16 w-16 -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-200/58 shadow-[0_0_14px_rgba(103,232,249,0.44)]" />
          <div className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-cyan-100 shadow-[0_0_14px_rgba(103,232,249,0.75)]" />
          <TMark style={{ bottom: "7%", left: "12%" }} />
          <TMark style={{ bottom: "7%", left: "39%" }} />
          <TMark style={{ bottom: "7%", right: "39%" }} />
          <TMark style={{ bottom: "7%", right: "12%" }} />
          <TMark style={{ top: "8%", left: "24%" }} />
          <TMark style={{ top: "8%", right: "24%" }} />
          <GoalPosts style={{ top: "-17%" }} />
          <GoalPosts style={{ bottom: "-13%" }} inverted />
        </div>
      </div>

      <div className="relative z-20 flex min-h-[700px] flex-col justify-between gap-4">
        {children}
      </div>
    </div>
  );
}

function FieldLine({
  dashed = false,
  style,
  strength = "soft",
}: {
  dashed?: boolean;
  style: CSSProperties;
  strength?: "soft" | "medium" | "strong";
}) {
  const opacity =
    strength === "strong"
      ? "border-cyan-100/70"
      : strength === "medium"
        ? "border-cyan-100/50"
        : "border-cyan-100/30";
  const width = strength === "strong" ? "border-t-2" : "border-t";
  const borderStyle = dashed ? "border-dashed" : "border-solid";

  return (
    <div
      className={`absolute inset-x-[6%] ${width} ${borderStyle} ${opacity} shadow-[0_0_12px_rgba(0,179,255,0.5)]`}
      style={style}
    />
  );
}

function DashedGuide({ side }: { side: "left" | "right" }) {
  return (
    <div
      className={`absolute top-[8%] h-[84%] border-l-2 border-dashed border-cyan-300/65 shadow-[0_0_12px_rgba(0,179,255,0.6)] ${
        side === "left" ? "left-[22%] -skew-x-[7deg]" : "right-[22%] skew-x-[7deg]"
      }`}
    />
  );
}

function FieldLabel({
  side,
  style,
  text,
}: {
  side: "left" | "right";
  style: CSSProperties;
  text: string;
}) {
  return (
    <span
      className={`absolute -translate-y-1/2 text-sm font-black leading-none text-cyan-300/80 drop-shadow-[0_0_9px_rgba(0,179,255,0.85)] [writing-mode:vertical-rl] ${
        side === "left" ? "left-[20.5%]" : "right-[20.5%]"
      }`}
      style={style}
    >
      {text}
    </span>
  );
}

function TMark({ style }: { style: CSSProperties }) {
  return (
    <div className="absolute h-8 w-8" style={style}>
      <div className="absolute left-1/2 top-0 h-8 border-l-2 border-cyan-300/70 shadow-[0_0_10px_rgba(0,179,255,0.7)]" />
      <div className="absolute left-0 right-0 top-0 border-t-2 border-cyan-300/70 shadow-[0_0_10px_rgba(0,179,255,0.7)]" />
    </div>
  );
}

function GoalPosts({
  inverted = false,
  style,
}: {
  inverted?: boolean;
  style: CSSProperties;
}) {
  return (
    <div
      className={`absolute left-1/2 h-8 w-16 -translate-x-1/2 ${
        inverted ? "rotate-180" : ""
      }`}
      style={style}
    >
      <div className="absolute left-1/2 top-0 h-10 border-l-2 border-cyan-50/80 shadow-[0_0_12px_rgba(226,246,255,0.72)]" />
      <div className="absolute left-3 top-0 h-8 border-l-2 border-cyan-50/80 shadow-[0_0_12px_rgba(226,246,255,0.72)]" />
      <div className="absolute right-3 top-0 h-8 border-l-2 border-cyan-50/80 shadow-[0_0_12px_rgba(226,246,255,0.72)]" />
      <div className="absolute left-3 right-3 top-2 border-t-2 border-cyan-50/80 shadow-[0_0_12px_rgba(226,246,255,0.72)]" />
    </div>
  );
}
