    function won(n){ return n.toLocaleString("ko-KR") + "원"; }

    // 오늘의 가격 계산: 도매최고가 x1.2 -> 1000원 올림(만원 미만이면 만원) = 4kg
    //                  4kg/2 -> 만원 이하 +1000, 만원 초과 +2000 = 2kg
    function todayPrices(maxPrice){
      const raw = maxPrice * 1.2;
      const p4 = raw < 10000 ? 10000 : Math.ceil(raw / 1000) * 1000;
      const half = Math.floor(p4 / 2 / 1000) * 1000;   // 절반을 1000원 단위로 내림
      const p2 = half <= 10000 ? half + 1000 : half + 2000;
      return { p4, p2 };
    }

    (async function(){
      try {
        const res = await fetch("price.json?t=" + Date.now());
        if(!res.ok) throw 0;
        const d = await res.json();
        if(d.maxPrice != null){
          const { p4, p2 } = todayPrices(d.maxPrice);
          document.getElementById("price4").textContent = won(p4);
          document.getElementById("price2").textContent = won(p2);

          // 한국시간 기준 오늘 날짜(YYYY-MM-DD)와 현재 시(0~23)
          const nowKST = new Date();
          const todayKST = new Intl.DateTimeFormat("en-CA",
            { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(nowKST);
          const hourKST = parseInt(new Intl.DateTimeFormat("en-GB",
            { timeZone: "Asia/Seoul", hour: "2-digit", hourCycle: "h23" }).format(nowKST), 10);

          // 어제(한국시간) 날짜 — 새벽엔 아직 오늘 경매 전이라 '어제'가 최신 기준
          const yesterdayKST = new Intl.DateTimeFormat("en-CA",
            { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" })
            .format(new Date(nowKST.getTime() - 86400000));

          let metaHTML =
            "시세를 반영해 매일 아침 새로 책정돼요<br>";
            
          // 휴무 판정: 7시 이후엔 오늘 경매가, 새벽(0~7시)엔 어제 경매가가 있어야 정상
          const isMarketClosed =
            (hourKST >= 7 && d.date !== todayKST) ||
            (hourKST < 7 && d.date !== yesterdayKST);

          if (isMarketClosed) {
            metaHTML +=
              "<div class='price-note'>장이 쉬는 날엔 직전 경매가를 기준 삼아요</div>";
          }

          metaHTML += "<span class='meta-date'>" + d.date + " 도매가 기준</span>";

          
          document.getElementById("priceMeta").innerHTML = metaHTML;

          document.getElementById("priceBox").style.display = "flex";

          if (d.briefing) {
            document.getElementById("briefingText").textContent = d.briefing;
            document.getElementById("briefing").style.display = "flex";
          }
        }
      } catch(e){ /* 가격 정보 없으면 조용히 숨김 */ }
    })();

    // 지도 링크 (네이버 지도 검색)
    (function(){
      const addr = "전북특별자치도 김제시 백구면 황토로 1079-25";
      document.getElementById("mapLink").href =
        "https://map.naver.com/p/search/" + encodeURIComponent(addr);
    })();

    // 품종 캐러셀: 모바일 스와이프 + PC 마우스 드래그 + 점 클릭, 항상 스냅
    (function(){
      const track = document.getElementById("vTrack");
      const dotsWrap = document.getElementById("vDots");
      if(!track || !dotsWrap) return;
      const panels = track.children.length;

      // 점 생성 + 클릭 이동
      for(let i=0;i<panels;i++){
        const d = document.createElement("span");
        d.className = "d" + (i===0 ? " on" : "");
        dotsWrap.appendChild(d);
      }
      const dots = dotsWrap.children;
      function setActive(i){
        i = Math.max(0, Math.min(panels-1, i));
        for(let k=0;k<dots.length;k++) dots[k].classList.toggle("on", k===i);
      }

      // 스크롤 위치에 따라 활성 점 갱신
      let raf = false;
      track.addEventListener("scroll", function(){
        if(!raf){ requestAnimationFrame(function(){ raf=false; setActive(Math.round(track.scrollLeft/track.clientWidth)); }); raf=true; }
      }, { passive: true });

      // PC 마우스 드래그
      let down=false, startX=0, startL=0, moved=false;
      track.addEventListener("mousedown", function(e){
        down=true; moved=false; startX=e.pageX; startL=track.scrollLeft;
        track.classList.add("dragging"); track.style.scrollSnapType="none"; e.preventDefault();
      });
      window.addEventListener("mousemove", function(e){
        if(!down) return;
        const dx = e.pageX - startX;
        if(Math.abs(dx) > 3) moved = true;
        track.scrollLeft = startL - dx;
      });
      window.addEventListener("mouseup", function(){
        if(!down) return;
        down=false; track.classList.remove("dragging"); track.style.scrollSnapType="";
        const i = Math.round(track.scrollLeft / track.clientWidth);
        track.scrollTo({ left: i*track.clientWidth, behavior:"smooth" });
      });
      // 드래그 직후 클릭(텍스트 선택 등) 무시
      track.addEventListener("click", function(e){ if(moved){ e.preventDefault(); e.stopPropagation(); } }, true);
    })();

    // 스크롤 등장 모션
    const io = new IntersectionObserver((entries)=>{
      entries.forEach(e=>{ if(e.isIntersecting){ e.target.classList.add("in"); io.unobserve(e.target);} });
    }, { threshold: 0.12 });
    document.querySelectorAll(".reveal").forEach(el=>io.observe(el));
