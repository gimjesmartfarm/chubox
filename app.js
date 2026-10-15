    function won(n){ return n.toLocaleString("ko-KR") + "원"; }

    // 오늘의 가격 계산: 도매최고가 x1.2 -> 1000원 올림(만원 미만이면 만원) = 4kg
    //                  4kg/2 -> 1000원 단위 내림, 만원 이하 +1000 / 만원 초과 +2000 = 2kg
    function todayPrices(maxPrice){
      const raw = maxPrice * 1.2;
      const p4 = raw < 10000 ? 10000 : Math.ceil(raw / 1000) * 1000;
      const half = Math.floor(p4 / 2 / 1000) * 1000;
      const p2 = half <= 10000 ? half + 1000 : half + 2000;
      return { p4, p2 };
    }

    let regionData = null;

    (async function(){
      try {
        const res = await fetch("price.json?t=" + Date.now());
        if(!res.ok) throw 0;
        const d = await res.json();
        if(d.maxPrice != null){
          const { p4, p2 } = todayPrices(d.maxPrice);
          document.getElementById("price4").textContent = won(p4);
          document.getElementById("price2").textContent = won(p2);

          // 한국시간 기준 오늘 날짜와 현재 시
          const nowKST = new Date();
          const todayKST = new Intl.DateTimeFormat("en-CA",
            { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(nowKST);
          const hourKST = parseInt(new Intl.DateTimeFormat("en-GB",
            { timeZone: "Asia/Seoul", hour: "2-digit", hourCycle: "h23" }).format(nowKST), 10);
          const yesterdayKST = new Intl.DateTimeFormat("en-CA",
            { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" })
            .format(new Date(nowKST.getTime() - 86400000));

          // 휴무 판정: 8시 이후엔 오늘, 새벽(0~8시)엔 오늘 또는 어제 경매가가 있어야 정상
          const isMarketClosed =
            (hourKST >= 8 && d.date !== todayKST) ||
            (hourKST <  8 && d.date !== todayKST && d.date !== yesterdayKST);

          let metaHTML = "시세를 반영해 매일 아침 새로 책정돼요<br>";
          if (isMarketClosed) {
            metaHTML += "<div class='price-note'>장이 쉬는 날엔 직전 경매가를 기준 삼아요</div>";
          }
          metaHTML += "<span class='meta-date'>" + d.date + " 도매가 기준</span>";
          document.getElementById("priceMeta").innerHTML = metaHTML;

          // 배경 추세 그래프 — 부드러운 곡선 버전
          if (Array.isArray(d.history) && d.history.length >= 2) {
            const vals = d.history.map(h => h.maxPrice);
            const min  = Math.min(...vals);
            const max  = Math.max(...vals);
            const span = max - min || 1;
            const n    = vals.length;
            const pts  = vals.map((v, i) => ({
              x: (i / (n - 1)) * 100,
              y: 38 - ((v - min) / span) * 34
            }));

            // 큐빅 베지어로 부드러운 곡선 생성
            function smooth(p, tension = 0.2) {
              let d = "M " + p[0].x.toFixed(1) + " " + p[0].y.toFixed(1);
              for (let i = 0; i < p.length - 1; i++) {
                const cur  = p[i];
                const next = p[i + 1];
                const prev = p[i - 1] || cur;
                const far  = p[i + 2] || next;
                const cp1x = cur.x  + (next.x - prev.x) * tension;
                const cp1y = cur.y  + (next.y - prev.y) * tension;
                const cp2x = next.x - (far.x  - cur.x)  * tension;
                const cp2y = next.y - (far.y  - cur.y)  * tension;
                d += " C " + cp1x.toFixed(1) + " " + cp1y.toFixed(1)
                   + " " + cp2x.toFixed(1) + " " + cp2y.toFixed(1)
                   + " " + next.x.toFixed(1) + " " + next.y.toFixed(1);
              }
              return d;
            }

            const line = smooth(pts);
            const area = line + " L 100 40 L 0 40 Z";

            document.getElementById("trend").innerHTML =
              "<path d='" + area + "' fill='rgba(29,122,62,0.05)'/>" +
              "<path d='" + line + "' fill='none' stroke='rgba(29,122,62,0.18)' stroke-width='1.8' " +
              "stroke-linejoin='round' stroke-linecap='round' vector-effect='non-scaling-stroke'/>";
          }

          // 지역별 도매가 범위 비교 (10박스 이상 최저~최고 상자 + 10박스 미만 이상치)
          const REGION_ORDER = ["익산","서울","인천","대구","대전","부산","광주","전주"];
          const regions = d.regions || {};
          const rnames = REGION_ORDER.filter(n => regions[n] && regions[n].maxPrice4kg > 0);
          if (rnames.length >= 2) {
            document.getElementById("regionBox").style.display = "flex";
            regionData = { regions, rnames };   // 가격박스까지 표시된 뒤 그림 (높이 확정 후)
            setupFlip();
          }

          document.getElementById("priceBox").style.display = "flex";

          if (d.briefing) {
            document.getElementById("briefingText").textContent = d.briefing;
            document.getElementById("briefing").style.display = "flex";
            document.getElementById("trend").style.display = "block";  // 그래프 같이 표시
          } else {
            document.getElementById("trend").style.display = "none";   // 브리핑 없으면 숨김
          }

          if (regionData) {
            const draw = () => renderRegions(regionData.regions, regionData.rnames);
            draw();
            // 박스 크기가 바뀌면(화면 회전·리사이즈) 다시 그림
            let rt, lastW = 0, lastH = 0;
            new ResizeObserver(([e]) => {
              const { width, height } = e.contentRect;
              if (Math.abs(width - lastW) < 1 && Math.abs(height - lastH) < 1) return;
              lastW = width; lastH = height;
              clearTimeout(rt); rt = setTimeout(draw, 100);
            }).observe(document.getElementById("regionBox"));
          }
        }
      } catch(e){ /* 가격 정보 없으면 조용히 숨김 */ }
    })();

    // ── 전국 도매가 비교: 가로 범위 막대 (10박스 이상 거래 최저~최고) ──
    function renderRegions(regions, rnames){
      const bars = document.getElementById("regionBars");
      const rows = rnames.map(n => {
        const r = regions[n], max = r.maxPrice4kg;
        return { n, r, max, min: r.minPrice4kg > 0 ? r.minPrice4kg : max };   // 구버전 데이터 호환
      });
      const lo = Math.min(...rows.map(x => x.min));
      const hi = Math.max(...rows.map(x => x.max));

      // 모바일처럼 좁으면 가격은 천원 단위, kg는 숫자만 (단위는 제목에)
      const compact = bars.clientWidth < 360;
      document.getElementById("regionTitle").textContent =
        "전국 도매가 비교 (4kg 기준" + (compact ? " · 천원 · kg)" : ")");
      const fp = v => compact ? (v / 1000).toFixed(v % 1000 ? 1 : 0) : v.toLocaleString("ko-KR");
      const fk = v => v.toLocaleString("ko-KR") + (compact ? "" : "kg");

      bars.innerHTML = rows.map(x =>
        "<div class='rr" + (x.n === "익산" ? " me" : "") + "'>"
        + "<div class='nm'>" + x.n + "<small>" + (x.r.date || "").slice(5).replace("-", "/") + "</small></div>"
        + "<div class='tr'></div>"
        + "<div class='kg'>" + (x.r.kg != null ? fk(x.r.kg) : "") + "</div>"
        + "</div>").join("");

      // 트랙 폭을 재서 픽셀 배치 — 양끝에 가격 라벨 자리 확보
      const trs = bars.querySelectorAll(".tr");
      // 위치는 calc(%)로 지정 → 카드 폭이 바뀌는 애니메이션 중에도 자연스럽게 늘어남
      const PAD = compact ? 26 : 46;
      const fr  = v => hi === lo ? 0.5 : (v - lo) / (hi - lo);
      const at  = (v, off) => "calc(" + (PAD + (off || 0)) + "px + (100% - " + PAD * 2 + "px) * " + fr(v).toFixed(4) + ")";

      rows.forEach((x, i) => {
        const w = "calc((100% - " + PAD * 2 + "px) * " + (fr(x.max) - fr(x.min)).toFixed(4) + ")";
        let h = "<div class='rg' style='left:" + at(x.min) + ";width:" + w + "'></div>"
              + "<i class='pt' style='left:" + at(x.max) + "'></i>"
              + "<span class='vl' style='left:" + at(x.max, 8) + "'>" + fp(x.max) + "</span>";
        if (x.min !== x.max)
          h += "<i class='pt' style='left:" + at(x.min) + "'></i>"
             + "<span class='vl l' style='left:" + at(x.min, -8) + "'>" + fp(x.min) + "</span>";
        trs[i].innerHTML = h;
      });
    }

    // ── 모바일: 카드 세 번 탭 → 뒤집기 ─────────────────────────────
    function setupFlip(){
      const flip = document.getElementById("flip");
      const row  = flip.closest(".price-row");
      const mq   = window.matchMedia("(max-width: 900px)");
      let count = 0, last = 0;
      flip.addEventListener("click", () => {
        if (!mq.matches) return;
        const now = Date.now();
        count = (now - last < 500) ? count + 1 : 1;
        last = now;
        if (count >= 3) {
          count = 0;
          const on = flip.classList.toggle("flipped");
          row.classList.toggle("wide", on);       // 뒤집히면 사진 폭까지 넓어짐
        }
      });
      mq.addEventListener("change", e => {
        if (!e.matches) { flip.classList.remove("flipped"); row.classList.remove("wide"); }
      });
    }

    // 지도 링크 (네이버 지도 검색)
    (function(){
      const addr = "전북특별자치도 김제시 백구면 황토로 1079-25";
      document.getElementById("mapLink").href =
        "https://map.naver.com/p/search/" + encodeURIComponent(addr);
    })();

    // 품종 캐러셀: 모바일 스와이프 + PC 마우스 드래그, 항상 스냅
    (function(){
      const track    = document.getElementById("vTrack");
      const dotsWrap = document.getElementById("vDots");
      if(!track || !dotsWrap) return;
      const panels = track.children.length;

      for(let i = 0; i < panels; i++){
        const d = document.createElement("span");
        d.className = "d" + (i === 0 ? " on" : "");
        dotsWrap.appendChild(d);
      }
      const dots = dotsWrap.children;
      function setActive(i){
        i = Math.max(0, Math.min(panels - 1, i));
        for(let k = 0; k < dots.length; k++) dots[k].classList.toggle("on", k === i);
      }

      let raf = false;
      track.addEventListener("scroll", function(){
        if(!raf){ requestAnimationFrame(function(){ raf = false; setActive(Math.round(track.scrollLeft / track.clientWidth)); }); raf = true; }
      }, { passive: true });

      let down = false, startX = 0, startL = 0, moved = false;
      track.addEventListener("mousedown", function(e){
        down = true; moved = false; startX = e.pageX; startL = track.scrollLeft;
        track.classList.add("dragging"); track.style.scrollSnapType = "none"; e.preventDefault();
      });
      window.addEventListener("mousemove", function(e){
        if(!down) return;
        const dx = e.pageX - startX;
        if(Math.abs(dx) > 3) moved = true;
        track.scrollLeft = startL - dx;
      });
      window.addEventListener("mouseup", function(){
        if(!down) return;
        down = false; track.classList.remove("dragging"); track.style.scrollSnapType = "";
        const i = Math.round(track.scrollLeft / track.clientWidth);
        track.scrollTo({ left: i * track.clientWidth, behavior: "smooth" });
      });
      track.addEventListener("click", function(e){ if(moved){ e.preventDefault(); e.stopPropagation(); } }, true);
    })();

    // 스크롤 등장 모션
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => { if(e.isIntersecting){ e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { threshold: 0.12 });
    document.querySelectorAll(".reveal").forEach(el => io.observe(el));
