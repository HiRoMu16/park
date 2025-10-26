# SLIP with Parallel Damper and Energy Injection: Policy Search via REINFORCE

本ディレクトリは，弾性脚モデル（SLIP: spring–loaded inverted pendulum）に並列ダンパと脚軸方向の定値エネルギ注入（Kitagawa 型）を付与した力学系に対して，
着地角度ポリシー（タッチダウン角度 α）を強化学習（REINFORCE）で探索し，安定かつ目標速度での走行を実現するためのコードです。

注意：本実装は物理モデルを厳密に組み込んだ「シミュレータ内学習」であり，狭義の Physics‑Informed Neural Network (PINN) ではありません。
ただし，力学的な整合性（アペックス機械エネルギ基準，立脚イベントの幾何，生存判定ゲート等）を報酬設計・学習過程に織り込む「physics‑informed な方策探索」という位置付けです。


## 特長と目的
- 目的速度 $v_{target}$（既定 3.33 m/s）での安定走行を達成する着地角ポリシーを学習
- 立脚フェーズの「最大圧縮→離地」区間で脚軸方向に一定力 f_in を注入（Kitagawa 型）
- 次アペックスの機械エネルギ $E_{apex_{end}}$ と参照エネルギ $E_{ref}$ の偏差に基づく $f_{in}$ の逐次更新
- Beta 分布方策で $α∈[αmin, αmax]$ を連続サンプリング（REINFORCE）
- 安定性・速度の2基準で成功判定，学習ログを CSV へ出力，学習後に GIF/MP4 を生成


## 力学モデル（概要）
- モデル：質点（質量 m）と質量のないばね脚（自然長 l0，剛性 k）＋並列ダンパ（粘性 c）
- 接地判定：フライト中に y ≤ l0 cos α かつ vy<0 を満たすとタッチダウン，足位置 xf = x + l0 sin α
- 立脚力：$F_{leg} = k(l0 − l) − c l̇$（伸長では 0）
- エネルギ注入：最大圧縮通過後〜離地まで Fin = const（歩内で定値），脚軸方向へ加算
- 運動方程式：$m \ddot{x} = (F_{leg}+F_{in}) ex，m \ddot{y} = (F_{leg}+F_{in}) ey − mg$（ex,ey は脚方向の単位ベクトル）
- 次アペックス検出：離地後，vy が正→0 に交差する時点をアペックスと定義


## 学習の定式化
- 観測：アペックスにおける obs = (vx, y)
- 行動：タッチダウン角 α（連続），Beta(a,b) を [αmin, αmax] に線形写像
- 報酬：$r = −((v_x − v_{target})/σv)^2 + r_{alive}$（途中で転倒/不成立時はペナルティ）
- エネルギ参照：$E_{ref} = 0.5 m v_{target}^2 + m g y_{apex_{ref}}$
- エネルギ注入更新（Kitagawa 風）：$f_{in} ← clip(f_{in} + K_f (E_{ref} − E_{apex_{end}}), 0..f_{in_{max}})$
- 安定性ゲート：ウォームアップ後，最大圧縮通過済みかつ lift‑off 直前 $vy_{lo_{raw}}$ < 閾値 なら不成立終了
- カリキュラム：一定エピソード経過後に α 範囲拡大，σv・r_alive・転倒ペナルティを厳格化


## 成功判定とログ
- succ_stab：エピソード内の歩数が指定閾値以上かつ未終了
- succ_speed：平均絶対誤差 ≤ 閾値 または 速度帯域（±band）内の歩割合 ≥ 指定比率
- succ_both：上記両方を満たす
- CSV 列：ep, loss, ret_start, steps_mean, succ_stab, succ_speed, succ_both, |vx−v*| 平均誤差，vy_lo_raw 平均，f_in 平均，stance/flight 時間，最小脚長，歩幅，E_apex 平均，終了理由トップ3


## ファイル構成
- slip-reinforce.py：主スクリプト（環境定義，REINFORCE 学習，可視化）
- train_log.csv：学習ログ（実行後に生成/更新）
- slip_run.gif：学習済みポリシーの可視化（実行後に生成）
- slip_run.mp4：MP4 出力（環境により生成失敗時は GIF のみ）
- result02.txt：実験メモ/出力例（参考）
- test.ipynb：軽微な確認用ノートブック


## 依存関係
- Python 3.9+
- numpy, torch, matplotlib, imageio (imageio-ffmpeg があると MP4 出力が安定)

例：
- pip install numpy torch matplotlib imageio imageio-ffmpeg


## 実行方法
- 学習＋可視化（GIF/MP4 生成まで）
  - python slip-reinforce.py
- ログ確認
  - train_log.csv を任意の可視化ツールで閲覧（損失，成功率，速度誤差など）
- 生成物
  - train_log.csv, slip_run.gif（と可能なら slip_run.mp4）

備考：現状ポリシーの重みはファイル保存していません。必要に応じて `reinforce_train()` の戻り値を `torch.save()` で保存してください。


## 主なハイパーパラメータ（HP dataclass）
- 物理：m, l0, k, c, g, dt
- 行動範囲：alpha_min_deg, alpha_max_deg（カリキュラム後に拡大）
- 目標：v_target, y_apex_ref, σv, r_alive, fall_penalty
- エネルギ注入：f_in0, Kf, f_in_max
- 学習：gamma, lr, batch_episodes, max_episodes, max_steps_per_ep
- 成功判定：success_steps_required, success_speed_avg_err_thresh, success_speed_band, success_speed_band_ratio
- ゲート/カリキュラム：use_viability_gate, vy_lo_min_late, gate_warmup_off_episodes, strict_* 系
- ログ/乱数：csv_path, seed

各値は `slip-reinforce.py` 冒頭の `HP` で一括管理されています。


## 実装メモ（式の対応）
- タッチダウン幾何：y ≤ l0 cos α, xf = x + l0 sin α
- 立脚力：Fleg = max(0, k(l0 − l) − c l̇)
- 運動学：ex,ey = (rx,ry)/l，a = ((Fleg+Fin)/m)[ex,ey] − [0,g]
- アペックス：vy が正から 0 に到達する時刻
- エネルギ：E = 0.5 m (vx²+vy²) + m g y（apex では vy=0）
- 注入更新：f_in ← clip(f_in + Kf (E_ref − E_apex_end), 0..f_in_max)


## PINN との関係（補足）
- 本コードは RL による方策探索ですが，物理整合性を強く活用しており「physics‑informed policy search」と言えます。
- 厳密な PINN 化の案：
  - 立脚/フライト ODE 残差を損失に組込み，方策やエネルギ更新のパラメータを同時最適化
  - アペックス境界条件（vy=0，接地/離地幾何）のソフト拘束化
  - シミュレータの微分可能化（イベントのスムージング）により端点感度を学習へ反映


## 既知の注意点
- MP4 生成は環境依存（codec=libx264 が使えない場合は GIF のみ保存）
- シード固定は行っていますが，RL の性質上ばらつきあり（ログで追跡可能）
- `max_time_per_step` や成功基準を厳しくすると探索難度が上がります


## 参考
- Blickhan (1989) “The spring–mass model for running and hopping”
- McMahon & Cheng (1990) “The mechanics of running: how does stiffness couple with speed?”
- Kitagawa 型のエネルギ注入：アペックス機械エネルギの差分に基づく逐次更新（本実装では式(7) 風の単純形を採用）

---
連絡先・補足や再現実験の希望があれば issue / PR を歓迎します。
