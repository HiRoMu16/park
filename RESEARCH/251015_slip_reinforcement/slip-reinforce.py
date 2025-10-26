# -*- coding: utf-8 -*-
"""
SLIP + Parallel Damper + Kitagawa-Style Energy Injection + REINFORCE(Beta)
- 立脚の「最大圧縮 → 離地」で脚軸方向へ一定力 f_in を注入（Kitagawa）
- 次歩の注入力更新: f_in <- clip(f_in + Kf*(E_ref - E_apex_end), 0..f_in_max)
  ※ E_apex_end は「当該歩の次アペックス（フライト期頂点）の機械エネルギ」
- 学習ログをCSV出力、学習後にGIF/MP4保存
- 成功判定を3種で記録: succ_stab（安定性）/ succ_speed（速度）/ succ_both（両方）
"""

import math, random, csv, os
from dataclasses import dataclass
from collections import Counter
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
import imageio.v2 as imageio
import matplotlib.pyplot as plt

# ==================== ハイパーパラメータ ====================
@dataclass
class HP:
    # 物理（既存研究の同定オーダに整合）
    m: float = 72.0
    l0: float = 1.00
    k: float = 28000.0         # [N/m] 20–32 kN/m 域
    c: float = 180.0           # [N·s/m] 67–264 Ns/m 域
    g: float = 9.81
    dt: float = 0.001

    # 行動レンジ（タッチダウン角）
    alpha_min_deg: float = 8.0
    alpha_max_deg: float = 22.0

    # シミュレーション
    max_time_per_step: float = 1.5

    # 目標・報酬
    v_target: float = 3.33
    y_apex_ref: float = 1.05     # 参照アペックス高
    sigma_v: float = 1.0         # → 後半 0.5
    r_alive: float = 0.8         # → 後半 0.3
    fall_penalty: float = 1.0    # → 後半 5.0

    # エネルギ注入（Kitagawa）
    f_in0: float = 120.0         # [N] 初期注入力
    Kf: float = 1.0              # [N/J] E誤差→次歩 f_in 更新ゲイン（0.5–2.0 を推奨）
    f_in_max: float = 600.0      # [N] 上限

    # ゲート（後半のみ有効）
    use_viability_gate: bool = True
    vy_lo_min_late: float = 0.15
    gate_warmup_off_episodes: int = 300

    # 学習
    gamma: float = 0.99
    lr: float = 2e-3
    batch_episodes: int = 30
    max_episodes: int = 800
    max_steps_per_ep: int = 20  # 1エピソードあたりの最大歩数（安定性成功の基準歩数のデフォルト）

    # カリキュラム（後半で厳格化）
    strict_sigma_v: float = 0.5
    strict_r_alive: float = 0.3
    strict_fall_penalty: float = 5.0
    strict_alpha_min_deg: float = 8.0
    strict_alpha_max_deg: float = 24.0

    # ---------- 成功判定（ユーザが変更しやすいよう分離） ----------
    # 安定性成功の必要歩数（例：全歩 = max_steps_per_ep、あるいは8割など）
    success_steps_required: int = 20    # ← ここを変えれば「成功の歩数」を変更できます
    # 速度成功：平均絶対誤差の上限（m/s）
    success_speed_avg_err_thresh: float = 0.4
    # 速度成功：帯域内（±band）に入った歩の割合（例：80%以上）
    success_speed_band: float = 0.5     # m/s
    success_speed_band_ratio: float = 0.8

    # ログ
    csv_path: str = "train_log.csv"

    # 乱数
    seed: int = 42

HP = HP()
ALPHA_MIN = math.radians(HP.alpha_min_deg)
ALPHA_MAX = math.radians(HP.alpha_max_deg)
random.seed(HP.seed); np.random.seed(HP.seed); torch.manual_seed(HP.seed)

# ==================== ユーティリティ ====================
def mech_energy(m,g,x,y,vx,vy):
    return 0.5*m*(vx*vx + vy*vy) + m*g*y

def safe_E_apex_from_obs(nxt):
    """obs=(vx,y) から 'vy≈0, x=0' としてアペックス機械エネルギを近似"""
    vx, y = float(nxt[0]), float(nxt[1])
    return mech_energy(HP.m, HP.g, 0.0, y, vx, 0.0)


# ==================== 環境 ====================
class SLIPEnv:
    """
    2D SLIP with Parallel Damper and Kitagawa-style Energy Injection
    - 立脚: 最大圧縮→離地の区間で脚軸方向に一定力 f_in を印加（同一区間内では定値）
    - f_in 更新（Kitagawa Eq.7）: 当該歩の「次アペックス（フライト期頂点）」エネルギ E_apex_end を用いる
      f_in <- clip(f_in + Kf*(E_ref - E_apex_end), 0..f_in_max)
    """
    def __init__(self):
        self.m, self.l0, self.k, self.c, self.g, self.dt = HP.m, HP.l0, HP.k, HP.c, HP.g, HP.dt
        self.reset()
        self.f_in = HP.f_in0

    def reset(self, v0=HP.v_target, y_apex=None):
        y_apex = self.l0 + 0.05 if y_apex is None else y_apex
        self.x, self.y = 0.0, y_apex
        self.vx, self.vy = float(v0), 0.0
        self.t, self.alive = 0.0, True
        # 参照エネルギ（vy≈0 を仮定）
        self.E_ref = 0.5*HP.m*(HP.v_target**2) + HP.m*HP.g*HP.y_apex_ref
        return np.array([self.vx, self.y], dtype=np.float32)

    def _term(self, reason, reward=None, extra=None, trace=None):
        obs = np.array([self.vx, self.y], dtype=np.float32)
        rew = -HP.fall_penalty if reward is None else reward
        info = {"reason": reason}
        if extra: info.update(extra)
        if trace is not None: info["trace"] = trace
        return obs, float(rew), True, info

    def simulate_one_step(self, alpha, max_time=HP.max_time_per_step, return_trace=False, episode_idx=1):
        if not self.alive: return self._term("dead")
        trace = [] if return_trace else None
        def push(xf=None, stance=False):
            if trace is not None: trace.append((self.x, self.y, xf, stance))

        x_start = self.x  # 歩幅算出用

        # ---- 遊脚：TD待ち ----
        time_used = 0.0
        while True:
            if time_used > max_time: self.alive=False; return self._term("timeout_flight", trace=trace)
            self.vy += -self.g*HP.dt; self.y += self.vy*HP.dt
            self.x += self.vx*HP.dt;  self.t += HP.dt; time_used += HP.dt
            push(None, False)
            if self.y <= 0.0: self.alive=False; return self._term("fall_in_flight", trace=trace)
            if (self.y <= self.l0*math.cos(alpha)) and (self.vy < 0.0):
                xf = self.x + self.l0*math.sin(alpha); break

        # ---- 立脚：最大圧縮→離地の注入，接地時間/最小脚長を計測 ----
        time_used = 0.0
        l_prev = None
        passed_max_comp = False
        stance_time = 0.0
        l_min = 1e9

        while True:
            if time_used > max_time: self.alive=False; return self._term("timeout_stance", trace=trace)
            rx, ry = self.x - xf, self.y
            l = math.hypot(rx, ry); l_min = min(l_min, l)
            if l >= self.l0: break  # 離地

            if l > 1e-8: ex, ey = rx/l, ry/l
            else:        ex, ey = 0.0, 1.0
            ldot = ex*self.vx + ey*self.vy

            if (l_prev is not None) and (not passed_max_comp):
                if ldot >= 0.0 and (l - l_prev) > -1e-10:
                    passed_max_comp = True
            l_prev = l

            Fleg = self.k*(self.l0 - l) - HP.c*ldot
            if Fleg < 0.0: Fleg = 0.0

            Fin = self.f_in if passed_max_comp else 0.0  # Kitagawa: 最大圧縮→離地で定値
            ax = ((Fleg + Fin)/self.m)*ex
            ay = ((Fleg + Fin)/self.m)*ey - self.g

            self.vx += ax*HP.dt; self.vy += ay*HP.dt
            self.x  += self.vx*HP.dt; self.y += self.vy*HP.dt
            self.t  += HP.dt; time_used += HP.dt; stance_time += HP.dt
            push(xf, True)

            if self.y <= 0.0 or l <= 0.2*self.l0:
                self.alive=False; return self._term("collapse", trace=trace)

        # 離地直後
        vy_lo_raw = self.vy
        extra = {"vy_lo_raw": float(vy_lo_raw), "passed_max_comp": passed_max_comp,
                 "f_in_now": float(self.f_in), "stance_time": float(stance_time), "l_min": float(l_min)}

        # 後半のみゲート（最大圧縮通過後の vy_lo_raw で判定）
        if HP.use_viability_gate and (episode_idx > HP.gate_warmup_off_episodes):
            if passed_max_comp and (vy_lo_raw < HP.vy_lo_min_late):
                self.alive=False; return self._term("no_apex_potential", reward=-0.5, extra=extra, trace=trace)

        # ---- 離地→次アペックス：E_apex_end を観測（ここが重要） ----
        prev_vy = self.vy
        time_used = 0.0
        flight_time = 0.0
        while True:
            if time_used > max_time: self.alive=False; return self._term("timeout_apex", extra=extra, trace=trace)
            self.vy += -self.g*HP.dt; self.y += self.vy*HP.dt
            self.x  += self.vx*HP.dt; self.t += HP.dt; time_used += HP.dt; flight_time += HP.dt
            push(None, False)
            if self.y <= 0.0: self.alive=False; return self._term("fall_before_apex", extra=extra, trace=trace)
            if prev_vy > 0.0 and self.vy <= 0.0:
                # 次アペックス到達（vy≈0）
                E_apex_end = mech_energy(self.m, self.g, self.x, self.y, self.vx, 0.0)
                extra["E_apex_end"] = float(E_apex_end)
                break
            prev_vy = self.vy

        # 次状態（アペックス観測）
        next_obs = np.array([self.vx, self.y], dtype=np.float32)
        step_length = self.x - x_start
        extra["flight_time"] = float(flight_time)
        extra["step_length"] = float(step_length)

        # 報酬
        rew = -((self.vx - HP.v_target)/HP.sigma_v)**2 + HP.r_alive
        extra["trace"] = trace

        # ===== Kitagawa Eq.(7): f_in 更新（フライト期アペックスのEを使用）=====
        E_err = self.E_ref - extra["E_apex_end"]
        self.f_in = min(max(self.f_in + HP.Kf*E_err, 0.0), HP.f_in_max)

        return next_obs, float(rew), False, extra

# ==================== 方策（Beta） ====================
class PolicyBeta(nn.Module):
    def __init__(self, obs_dim=2, hidden=64):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(obs_dim, hidden), nn.Tanh(),
                                  nn.Linear(hidden, hidden), nn.Tanh())
        self.head = nn.Linear(hidden, 2)
    def forward(self, x):
        if x.dim()==1: x=x.unsqueeze(0)
        h=self.body(x); raw=self.head(h)
        a=F.softplus(raw[...,0])+1.0; b=F.softplus(raw[...,1])+1.0
        return a.squeeze(-1), b.squeeze(-1)
    def sample_action(self, obs):
        a,b=self.forward(obs); dist=torch.distributions.Beta(a,b)
        z=dist.rsample(); logp=dist.log_prob(z)
        alpha=ALPHA_MIN+(ALPHA_MAX-ALPHA_MIN)*z
        return alpha.squeeze(), logp.squeeze()
    def deterministic_action(self, obs):
        a,b=self.forward(obs); z=a/(a+b)
        return (ALPHA_MIN+(ALPHA_MAX-ALPHA_MIN)*z).squeeze()

# ==================== 学習（REINFORCE） ====================
def reinforce_train():
    env = SLIPEnv()
    policy = PolicyBeta()
    optim = torch.optim.Adam(policy.parameters(), lr=HP.lr)

    # CSV 初期化
    with open(HP.csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ep","loss","ret_start","steps_mean",
                    "succ_stab","succ_speed","succ_both",
                    "abs_err_mean","vy_lo_raw_mean","f_in_mean",
                    "stance_time_mean","flight_time_mean","l_min_mean",
                    "step_length_mean","E_apex_end_mean","reasons_top"])

    def run_episode(ep_idx):
        obs = env.reset()
        traj_logp, traj_ret = [], []
        done, reason = False, "success"

        # 集計用
        steps = 0
        abs_err_acc = 0.0
        band_count = 0  # 速度帯域内カウント
        vy_sum = fin_sum = stance_sum = flight_sum = lmin_sum = sl_sum = Eapex_sum = 0.0

        for _ in range(HP.max_steps_per_ep):
            obs_t = torch.from_numpy(obs).float()
            alpha, logp = policy.sample_action(obs_t)
            nxt, rew, done, info = env.simulate_one_step(float(alpha.item()),
                                                         return_trace=False, episode_idx=ep_idx)
            traj_logp.append(logp); traj_ret.append(rew)
            steps += 1
            vx_now = float(nxt[0])
            abs_err_acc += abs(vx_now - HP.v_target)
            if abs(vx_now - HP.v_target) <= HP.success_speed_band:
                band_count += 1

            vy_sum  += float(info.get("vy_lo_raw", 0.0))
            fin_sum += float(info.get("f_in_now", 0.0))
            stance_sum += float(info.get("stance_time", 0.0))
            flight_sum += float(info.get("flight_time", 0.0))
            lmin_sum += float(info.get("l_min", 0.0))
            sl_sum   += float(info.get("step_length", 0.0))
            Eapex_sum += float(info.get("E_apex_end", safe_E_apex_from_obs(nxt)))

            if done:
                reason = info.get("reason","unknown"); break
            obs = nxt

        # 割引和→標準化
        R=0.0; returns=[]
        for r in reversed(traj_ret): R = r + HP.gamma*R; returns.append(R)
        returns.reverse()
        Gt = torch.tensor(returns, dtype=torch.float32)
        if len(Gt)>1: Gt = (Gt - Gt.mean())/(Gt.std()+1e-8)

        # 成功判定（3種）
        avg_abs_err = abs_err_acc / max(1, steps)
        success_stab  = (not done) and (steps >= HP.success_steps_required)
        success_speed = (avg_abs_err <= HP.success_speed_avg_err_thresh) or \
                        (band_count / max(1, steps) >= HP.success_speed_band_ratio)
        success_both  = success_stab and success_speed

        stats = {
            "steps": steps,
            "success_stab": success_stab,
            "success_speed": success_speed,
            "success_both": success_both,
            "reason": reason,
            "abs_err": avg_abs_err,
            "vy_mean": vy_sum/max(1,steps),
            "fin_mean": fin_sum/max(1,steps),
            "stance_mean": stance_sum/max(1,steps),
            "flight_mean": flight_sum/max(1,steps),
            "lmin_mean": lmin_sum/max(1,steps),
            "sl_mean": sl_sum/max(1,steps),
            "Eapex_mean": Eapex_sum/max(1,steps)
        }
        return traj_logp, Gt, stats

    for ep in range(1, HP.max_episodes+1):
        # カリキュラム切替
        if ep == HP.gate_warmup_off_episodes + 1:
            HP.sigma_v = HP.strict_sigma_v; HP.r_alive = HP.strict_r_alive
            HP.fall_penalty = HP.strict_fall_penalty
            global ALPHA_MIN, ALPHA_MAX
            ALPHA_MIN = math.radians(HP.strict_alpha_min_deg)
            ALPHA_MAX = math.radians(HP.strict_alpha_max_deg)

        batch_loss=0.0
        ret0L, stepsL, succStabL, succSpdL, succBothL, errL = [], [], [], [], [], []
        vyL, finL, stL, ftL, lminL, slL, EapexL = [], [], [], [], [], [], []
        reasons = Counter()

        for _ in range(HP.batch_episodes):
            logps, Gt, st = run_episode(ep)
            if len(logps)==0: continue
            loss = -(torch.stack(logps) * Gt).sum()
            batch_loss += loss.item()
            optim.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 5.0)
            optim.step()

            ret0L.append(Gt[0].item()); stepsL.append(st["steps"])
            succStabL.append(1.0 if st["success_stab"]  else 0.0)
            succSpdL.append(1.0 if st["success_speed"] else 0.0)
            succBothL.append(1.0 if st["success_both"]  else 0.0)
            errL.append(st["abs_err"]); vyL.append(st["vy_mean"]); finL.append(st["fin_mean"])
            stL.append(st["stance_mean"]); ftL.append(st["flight_mean"])
            lminL.append(st["lmin_mean"]); slL.append(st["sl_mean"]); EapexL.append(st["Eapex_mean"])
            reasons[st["reason"]] += 1

        if ep % 10 == 0:
            topR = ", ".join([f"{k}:{v}" for k,v in reasons.most_common(3)])
            loss_mean = batch_loss/HP.batch_episodes if HP.batch_episodes>0 else float("nan")
            print(f"[Ep {ep:4d}] loss={loss_mean:.3f} ret@start={np.mean(ret0L):.3f} "
                  f"steps={np.mean(stepsL):.1f} succ_stab={np.mean(succStabL):.2f} "
                  f"succ_speed={np.mean(succSpdL):.2f} succ_both={np.mean(succBothL):.2f} "
                  f"|vx-3.33|={np.mean(errL):.3f} vy_lo_raw={np.mean(vyL):.3f} "
                  f"f_in={np.mean(finL):.1f} stance={np.mean(stL):.3f} flight={np.mean(ftL):.3f} "
                  f"l_min={np.mean(lminL):.3f} stepL={np.mean(slL):.3f} E_apex={np.mean(EapexL):.1f} "
                  f"reasons=[{topR}]")

        # CSV 追記
        with open(HP.csv_path, "a", newline="") as f:
            w = csv.writer(f)
            topR = ", ".join([f"{k}:{v}" for k,v in reasons.most_common(3)])
            loss_mean = batch_loss/HP.batch_episodes if HP.batch_episodes>0 else float("nan")
            w.writerow([ep, loss_mean, np.mean(ret0L), np.mean(stepsL),
                        np.mean(succStabL), np.mean(succSpdL), np.mean(succBothL),
                        np.mean(errL), np.mean(vyL), np.mean(finL),
                        np.mean(stL), np.mean(ftL), np.mean(lminL),
                        np.mean(slL), np.mean(EapexL), topR])
    return policy

# ==================== 可視化（GIF/MP4） ====================
def simulate_and_save_video(policy, gif_path="slip_run.gif", mp4_path="slip_run.mp4",
                            steps=8, stochastic=False, fps=60):
    # 1st pass: 軌道と画角
    env = SLIPEnv(); obs = env.reset(v0=HP.v_target)
    traces=[]; x_min=+1e9; x_max=-1e9; y_min=0.0
    for i in range(steps):
        obs_t=torch.from_numpy(obs).float()
        with torch.no_grad():
            alpha = policy.sample_action(obs_t)[0] if stochastic else policy.deterministic_action(obs_t)
        nxt, r, done, info = env.simulate_one_step(float(alpha), return_trace=True,
                                                   episode_idx=HP.max_episodes+1)
        trace = info["trace"]; traces.append(trace)
        xs=[p[0] for p in trace]; ys=[p[1] for p in trace]
        if xs: x_min=min(x_min,min(xs)); x_max=max(x_max,max(xs))
        if ys: y_min=min(y_min,min(ys))
        if done: break
        obs=nxt
    x_pad=0.5; y_pad=0.2
    xlim=(x_min-x_pad, x_max+x_pad)
    ylim=(max(0.0,y_min-y_pad),
          max(1.2, max([max(p[1] for t in traces for p in t)] + [1.2]) + y_pad))

    # 描画→フレーム列
    frames=[]; every=max(1,int(1/(fps*HP.dt)))
    fig, ax = plt.subplots(figsize=(6,3))
    for step_idx, trace in enumerate(traces):
        for (x,y,xf,stance) in trace[::every]:
            ax.clear()
            ax.plot([xlim[0]-1, xlim[1]+1],[0,0], lw=2, c='k')
            if stance and xf is not None:
                ax.plot([xf,x],[0,y], lw=3); ax.scatter([xf],[0], s=30)
            ax.scatter([x],[y], s=80)
            ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.set_aspect('equal','box')
            ax.set_title(f"Step {step_idx+1}")
            fig.canvas.draw()
            buf = np.asarray(fig.canvas.buffer_rgba())
            frames.append(buf[...,:3].copy())
    plt.close(fig)

    imageio.mimsave(gif_path, frames, duration=1.0/fps)
    print(f"[GIF] saved -> {gif_path}")
    # MP4（ffmpeg が利用可能なら）
    try:
        with imageio.get_writer(mp4_path, fps=fps, codec="libx264", quality=8) as w:
            for fr in frames: w.append_data(fr)
        print(f"[MP4] saved -> {mp4_path}")
    except Exception as e:
        print(f"[MP4] failed ({e}). GIFのみ保存しました。")

# ==================== 実行 ====================
def quick_sanity_check():
    env=SLIPEnv(); obs=env.reset(v0=HP.v_target)
    nxt,r,done,info=env.simulate_one_step(math.radians(12.0), episode_idx=1)
    print("[Sanity] next_obs=",nxt," reward=",r," done=",done, info)

if __name__=="__main__":
    quick_sanity_check()
    pol = reinforce_train()
    simulate_and_save_video(pol, gif_path="slip_run.gif", mp4_path="slip_run.mp4",
                            steps=8, stochastic=False, fps=60)
