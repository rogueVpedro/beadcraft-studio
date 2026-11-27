// Hose Bead Mascot: 拼豆工坊专属 1930s 橡皮管卡通拼豆小精灵 (<hose-bead-mascot>)
// 严格遵循 rubber-hose-ui SKILL.md 规范，复用 window.RubberHose 24fps 共享时钟、白手套、大皮鞋与橡皮管四肢 API：
// 1. 真实可聚焦 <button class="hit"> 控件覆盖画布，支持键盘与点击互动
// 2. 四肢起点深入管状拼豆身体内部，扶腰手臂采用 reach() -> 身体 -> hand() 分层绘制，腿部精确裁切进皮鞋开口
// 3. 实时联动用户当前选中的拼豆色号（hex + code），点击或绘制时触发体积守恒挤压回弹与墨水放射线 ticks()
(() => {
function registerBeadMascot() {
  const fx = window.RubberHose;
  if (!fx) return;
  const { FPS, INK, TAU, clamp, ring, beat, esc, art, arm, reach, hand, leg, ticks, sfx, write } = fx;

  const LINES = [
    "嘿！选颗顺眼的豆子，咱开摆！",
    "BOP! 管状小拼豆今天精神百倍！",
    "按住空格拖画布，滚轮放大看色号！",
    "熨烫记得贴美纹纸，受热才均匀哟！",
    "想偷懒？让左边 AI 助手搜几张好图！",
  ];

  class HoseBeadMascot extends fx.Base {
    static delegates = true;
    size() { return [300, 210]; }
    render() {
      return `<button class="hit" type="button" aria-label="${esc(this.getAttribute("label") || "拼豆小精灵互动")}"></button>`;
    }

    setup() {
      const btn = this.$("button");
      const g = this.g;
      const popSfx = art("sfx-pop") || art("sfx-bop") || art("sfx-ding");
      let colorHex = this.getAttribute("color") || "#e4472c";
      let colorCode = this.getAttribute("code") || "F02";
      let textColor = "#ffffff";
      let excitedAt = -99;
      let lineIdx = 0;

      this.setBead = (hex, code, txtCol = "#ffffff", cheer = false) => {
        if (hex) colorHex = hex;
        if (code) colorCode = code;
        if (txtCol) textColor = txtCol;
        if (cheer && !fx.calm) {
          excitedAt = fx.now;
        }
      };

      this.bop = (customLine) => {
        excitedAt = fx.calm ? -99 : fx.now;
        if (customLine) {
          this.say(customLine);
        } else {
          lineIdx = (lineIdx + 1) % LINES.length;
          this.say(LINES[lineIdx]);
        }
      };

      btn.addEventListener("click", () => {
        this.bop();
        this.emit("bop", { code: colorCode, color: colorHex });
      });

      this.say(LINES[0]);

      this.frame = (t) => {
        const k = (t - excitedAt) * FPS;
        const calm = fx.calm;
        const cheering = !calm && k >= 0 && k < 18;
        const bob = calm ? 0 : beat(t, 0.18);
        const pop = calm ? 0 : ring(k, 14, 0.95, 3.4);

        const CX = 150;
        const FLOOR = 196;
        const R = 50;
        // 体积守恒挤压拉伸，锚定在双脚正上方
        const sy = (1 + 0.18 * pop + 0.035 * bob);
        const sx = 1 / Math.sqrt(Math.max(0.7, sy));
        const jumpY = cheering ? Math.max(0, Math.sin(clamp(k / 10) * Math.PI)) * 16 : 0;
        const cy = 104 - bob * 5 - jumpY;

        g.begin();

        // 地面浅墨投影
        g.fillStyle = "rgba(37, 29, 22, 0.16)";
        g.beginPath();
        g.ellipse(CX, FLOOR - 3, 46 - jumpY * 0.6, 8, 0, 0, TAU);
        g.fill();

        // 1. 先画双腿（起点深入拼豆圆环内部，末端裁切进皮鞋开口）
        const kick = cheering ? Math.sin(k * 0.7) * 8 : 0;
        leg(g, CX - 15, cy + R * 0.45, CX - 24 - Math.max(0, kick), FLOOR - 6 - Math.max(0, kick) * 0.5, -5, {
          dir: -1,
          w: 35,
          rot: cheering ? 0.18 : 0.04 * bob,
        });
        leg(g, CX + 15, cy + R * 0.45, CX + 24 + Math.max(0, -kick), FLOOR - 6 - Math.max(0, -kick) * 0.5, 5, {
          dir: 1,
          w: 35,
          rot: cheering ? -0.18 : -0.04 * bob,
        });

        // 2. 右侧挥手手臂（从身体内部伸出，白手套朝向观众）
        const wave = calm ? 0 : Math.sin(t * Math.PI * 2.1) * 7;
        if (cheering) {
          arm(g, "fist", CX - R * 0.55 * sx, cy - 2, CX - 90, cy - 26 - bob * 4, -9, { w: 28, turn: 0.2 });
          arm(g, "fist", CX + R * 0.55 * sx, cy - 2, CX + 90, cy - 26 - bob * 4, 9, { w: 28, turn: -0.2 });
        } else {
          arm(g, "palm", CX + R * 0.52 * sx, cy - 2, CX + 90, cy - 26 + wave, 9, { w: 29, turn: -0.2 });
        }

        // 3. 左侧叉腰手臂：严格遵循 SKILL.md 拆分规则 reach() -> 身体 -> hand()，外扩弧度露出完整橡皮管弯臂
        let hipAng = 0;
        const hipX = CX - R * 0.88 * sx;
        const hipY = cy + 16;
        if (!cheering) {
          hipAng = reach(g, CX - R * 0.62 * sx, cy - 10, hipX, hipY, -28, { w: 27, turn: 0.55 });
        }

        // 4. 绘制管状融合拼豆主体（全墨线描边 + 立体高光 + 中心孔）
        g.save();
        g.translate(CX, cy + R);
        g.scale(sx, sy);
        g.translate(0, -R);

        // 拼豆外圆与顶面厚度暗部
        g.fillStyle = colorHex;
        g.strokeStyle = INK;
        g.lineWidth = 4.2;
        g.beginPath();
        g.arc(0, 0, R, 0, TAU);
        g.fill();
        g.stroke();

        // 复古赛璐璐半月暗面与高光弧
        g.fillStyle = "rgba(37, 29, 22, 0.13)";
        g.beginPath();
        g.arc(0, 0, R - 2.5, 0.25, Math.PI - 0.25);
        g.quadraticCurveTo(0, R * 0.55, -(R - 2.5) * Math.cos(0.25), (R - 2.5) * Math.sin(0.25));
        g.fill();

        g.strokeStyle = "rgba(255, 250, 235, 0.68)";
        g.lineWidth = 4.5;
        g.beginPath();
        g.arc(0, 0, R - 9, Math.PI * 1.12, Math.PI * 1.56);
        g.stroke();

        // 管状拼豆标志性顶部中心圆孔（透出画纸底色与内壁墨线）
        g.fillStyle = "#ecd7ac";
        g.strokeStyle = INK;
        g.lineWidth = 3.4;
        g.beginPath();
        g.ellipse(0, -R * 0.62, 12.5, 5.6, 0, 0, TAU);
        g.fill();
        g.stroke();

        // 1930s 经典缺角扇形卡通眼（Pie-cut Eyes）
        for (const ex of [-13.5, 13.5]) {
          g.fillStyle = "#fff9e8";
          g.strokeStyle = INK;
          g.lineWidth = 2.8;
          g.beginPath();
          g.ellipse(ex, -9, 10, 12.8, 0, 0, TAU);
          g.fill();
          g.stroke();

          const px = ex + (ex < 0 ? 1.8 : -1.2);
          g.fillStyle = INK;
          g.beginPath();
          g.moveTo(px, -8);
          g.arc(px, -8, 5.8, 0.35, TAU - 0.35);
          g.closePath();
          g.fill();
        }

        // 宽弧度复古大笑嘴巴（清晰避开双眼与底部铭牌）
        g.strokeStyle = INK;
        g.lineWidth = 3.2;
        if (cheering) {
          g.fillStyle = "#8c1d0b";
          g.beginPath();
          g.arc(0, 5, 19, 0.14 * Math.PI, 0.86 * Math.PI);
          g.closePath();
          g.fill();
          g.stroke();
          g.fillStyle = "#f87171";
          g.beginPath();
          g.ellipse(0, 18, 8.5, 4.2, 0, 0, TAU);
          g.fill();
        } else {
          g.beginPath();
          g.arc(0, -1, 22, 0.22 * Math.PI, 0.78 * Math.PI);
          g.stroke();
          g.beginPath();
          g.arc(-17.5, 12.5, 3.2, -0.7, 1.3);
          g.moveTo(20.2, 10.5);
          g.arc(17.5, 12.5, 3.2, 1.8, 3.8);
          g.stroke();
        }

        // 肚子上的当前色号大字号铭牌
        g.fillStyle = "#fbe7c0";
        g.strokeStyle = INK;
        g.lineWidth = 2.4;
        g.beginPath();
        g.roundRect(-27, 24, 54, 22, 11);
        g.fill();
        g.stroke();
        write(g, colorCode, 0, 35.5, 17.5, { col: INK });

        g.restore();

        // 5. 补上叉腰前手白手套（覆盖在身体轮廓前方）
        if (!cheering) {
          hand(g, "knuckle", hipX, hipY, hipAng, 27, 1);
        }

        // 6. 欢呼时的放射墨水短线与手写音效词（置于头顶正上方空白区，绝不遮挡拳头或右侧文字）
        if (cheering) {
          if (k < 9) {
            ticks(g, CX, cy - 8, 7, 58 + k * 2, 70 + k * 3, -Math.PI * 0.88, -Math.PI * 0.12, 2.5, Math.floor(k / 2));
          }
          if (popSfx) {
            sfx(g, popSfx, 150, 22, 78, Math.floor(k / 2), 0.45, false, -0.05);
          }
        }
      };
    }
  }

  fx.define("hose-bead-mascot", HoseBeadMascot);
}

if (window.RubberHose) {
  registerBeadMascot();
} else {
  window.addEventListener("DOMContentLoaded", registerBeadMascot, { once: true });
}
})();
