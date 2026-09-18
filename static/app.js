async function postJSON(url,data){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const j=await r.json();if(!r.ok)throw Error(j.error||'Request failed');return j}
function wireAuth(){const form=document.querySelector('[data-auth]');if(!form)return;form.addEventListener('submit',async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(form));try{await postJSON(form.dataset.auth,d);location.href='/analyze'}catch(x){const m=document.querySelector('#msg');if(m)m.textContent=x.message}})}
function wireAnalyze(){const form=document.querySelector('#analyzeForm');if(!form)return;form.addEventListener('submit',async e=>{e.preventDefault();const btn=form.querySelector('button');const fd=new FormData(form);btn.disabled=true;btn.textContent='ANALYZING…';try{const r=await fetch('/api/analyze',{method:'POST',body:fd});const j=await r.json();if(!r.ok)throw Error(j.error);sessionStorage.setItem('lm_result',JSON.stringify(j));location.href='/results'}catch(x){const m=document.querySelector('#analysisMsg');if(m)m.textContent=x.message;btn.disabled=false;btn.textContent='RUN CORRESPONDENCE ANALYSIS'}})}
function renderResult(){const box=document.querySelector('#result');if(!box)return;const raw=sessionStorage.getItem('lm_result');const r=raw?JSON.parse(raw):null;if(!r){box.innerHTML='<div class="card"><h3>No recent analysis</h3><p class="muted">Run an analysis first.</p></div>';return}const meta=x=>`<table class="table"><tr><th>Latitude</th><td>${x.latitude??'Not available'}</td></tr><tr><th>Longitude</th><td>${x.longitude??'Not available'}</td></tr><tr><th>Altitude</th><td>${x.altitude??'Not available'}</td></tr><tr><th>Acquisition</th><td>${x.acquisition_time??'Not available'}</td></tr><tr><th>CRS / Projection</th><td>${x.crs??'Not available'} / ${x.projection??'Not available'}</td></tr><tr><th>Mission / Instrument</th><td>${x.mission??'Not available'} / ${x.camera??'Not available'}</td></tr></table>`;box.innerHTML=`<div class="metrics"><div class="card metric"><span class="muted">RELIABILITY</span><strong>${r.reliability}</strong></div><div class="card metric"><span class="muted">SCORE</span><strong>${r.score}%</strong></div><div class="card metric"><span class="muted">VERIFIED</span><strong>${r.verified_matches}</strong></div><div class="card metric"><span class="muted">INLIER RATIO</span><strong>${r.inlier_ratio}%</strong></div></div><br><div class="card"><h2>Correspondence Map</h2><img class="imgresult" src="${r.result_image}"><p class="muted">${r.validation_note}</p></div><br><div class="grid"><div class="card"><h2>Image A Metadata</h2>${meta(r.image_a.metadata)}</div><div class="card"><h2>Image B Metadata</h2>${meta(r.image_b.metadata)}</div><div class="card"><h2>Verification</h2><table class="table"><tr><th>Raw matches</th><td>${r.raw_matches}</td></tr><tr><th>Candidate matches</th><td>${r.candidate_matches}</td></tr><tr><th>Geometric consistency</th><td>${r.geometric_consistency}%</td></tr><tr><th>Feature coverage</th><td>${r.feature_coverage}%</td></tr><tr><th>Homography</th><td>${r.homography_status}</td></tr><tr><th>Processing</th><td>${r.processing_time_ms} ms</td></tr></table></div></div>`}
function parallax(){const back=document.querySelector('.star-layer-a'),mid=document.querySelector('.star-layer-b'),front=document.querySelector('.star-layer-c');if(!back)return;let tx=0,ty=0,cx=0,cy=0;window.addEventListener('pointermove',e=>{tx=(e.clientX/window.innerWidth-.5)*2;ty=(e.clientY/window.innerHeight-.5)*2});function frame(){cx+=(tx-cx)*.035;cy+=(ty-cy)*.035;back.style.transform=`translate3d(${cx*5}px,${cy*5}px,0)`;mid.style.transform=`translate3d(${cx*11}px,${cy*11}px,0)`;front.style.transform=`translate3d(${cx*18}px,${cy*18}px,0)`;requestAnimationFrame(frame)}frame()}
function cursor(){const g=document.querySelector('#cursor-glow');if(!g)return;let x=innerWidth/2,y=innerHeight/2,cx=x,cy=y;addEventListener('pointermove',e=>{x=e.clientX;y=e.clientY});function f(){cx+=(x-cx)*.07;cy+=(y-cy)*.07;g.style.left=cx+'px';g.style.top=cy+'px';requestAnimationFrame(f)}f()}
document.addEventListener('DOMContentLoaded',()=>{wireAuth();wireAnalyze();renderResult();parallax();cursor()});
function lmSmoothNavigation(){

  async function loadPage(url, push=true){

    try{

      const response = await fetch(url, {
        headers: {
          "X-Requested-With": "XMLHttpRequest"
        }
      });

      if(!response.ok){
        window.location.href = url;
        return;
      }

      const html = await response.text();
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, "text/html");

      const newContent = doc.querySelector("#page-content");
      const currentContent = document.querySelector("#page-content");

      if(!newContent || !currentContent){
        window.location.href = url;
        return;
      }

      currentContent.innerHTML = newContent.innerHTML;

      document.title = doc.title;

      if(push){
        history.pushState({}, "", url);
      }

      window.scrollTo(0, 0);

      wireAuth();
      wireAnalyze();
      renderResult();

      document.querySelectorAll(".reveal").forEach((el, index)=>{
        el.style.animationDelay = `${index * 70}ms`;
        el.classList.add("is-visible");
      });

    }catch(error){

      window.location.href = url;

    }

  }


  document.addEventListener("click", e=>{

    const link = e.target.closest("a[href]");

    if(!link) return;

    const href = link.getAttribute("href");

    if(
      !href ||
      href.startsWith("#") ||
      href.startsWith("http") ||
      href.startsWith("mailto:") ||
      href.startsWith("tel:") ||
      link.target === "_blank" ||
      link.hasAttribute("download")
    ){
      return;
    }

    const url = new URL(href, window.location.origin);

    if(url.origin !== window.location.origin){
      return;
    }

    e.preventDefault();

    loadPage(url.href);

  });


  window.addEventListener("popstate", ()=>{

    loadPage(window.location.href, false);

  });

}


document.addEventListener("DOMContentLoaded", lmSmoothNavigation);
requestAnimationFrame(()=>{
  document.body.classList.add("lm-ready");
});
/* =========================================================
   LUNARMATCH — MOBILE NAVIGATION
   ========================================================= */

/* =========================================================
   LUNARMATCH — MOBILE NAVIGATION
   ========================================================= */

function lmMobileNavigation() {

  const toggle = document.querySelector(".mobile-menu-toggle");
  const menu = document.querySelector("#mobile-navigation");

  if (!toggle || !menu) return;

  /* Prevent duplicate event listeners */
  if (toggle.dataset.mobileReady === "true") return;

  toggle.dataset.mobileReady = "true";

  function openMenu() {
    toggle.classList.add("is-open");
    menu.classList.add("is-open");

    toggle.setAttribute("aria-expanded", "true");
    toggle.setAttribute("aria-label", "Close navigation");

    menu.setAttribute("aria-hidden", "false");

    document.body.classList.add("mobile-nav-open");
  }

  function closeMenu() {
    toggle.classList.remove("is-open");
    menu.classList.remove("is-open");

    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Open navigation");

    menu.setAttribute("aria-hidden", "true");

    document.body.classList.remove("mobile-nav-open");
  }

  toggle.addEventListener("click", function(event) {

    event.preventDefault();
    event.stopPropagation();

    if (menu.classList.contains("is-open")) {
      closeMenu();
    } else {
      openMenu();
    }

  });

  menu.querySelectorAll("a").forEach(link => {

    link.addEventListener("click", () => {
      closeMenu();
    });

  });

  document.addEventListener("keydown", event => {

    if (
      event.key === "Escape" &&
      menu.classList.contains("is-open")
    ) {
      closeMenu();
    }

  });

}


/* INITIAL LOAD */

document.addEventListener("DOMContentLoaded", () => {
  lmMobileNavigation();
});
/* =========================================================
   LUNARMATCH — PROCEDURAL LUNAR SPHERE
   ========================================================= */

function initProceduralMoon() {

  const canvas =
    document.getElementById("lunar-surface-canvas");

  if (!canvas) return;

  if (canvas.dataset.ready === "true") return;

  canvas.dataset.ready = "true";

  const ctx =
    canvas.getContext("2d");

  const container =
    canvas.parentElement;

  let width = 0;
  let height = 0;
  let dpr = 1;

  let rotation = 0;

  const craters = [];

  /*
   * Generate stable lunar terrain.
   */
  for (let i = 0; i < 95; i++) {

    craters.push({
      longitude: Math.random() * Math.PI * 2,
      latitude:
        (Math.random() - .5) * Math.PI,

      radius:
        .012 + Math.random() * .045,

      depth:
        .25 + Math.random() * .65
    });
  }


  function resize() {

    const rect =
      container.getBoundingClientRect();

    const size =
      Math.max(
        120,
        Math.min(rect.width, rect.height)
      );

    dpr =
      Math.min(
        window.devicePixelRatio || 1,
        2
      );

    width = size;
    height = size;

    canvas.width =
      Math.floor(size * dpr);

    canvas.height =
      Math.floor(size * dpr);

    canvas.style.width =
      size + "px";

    canvas.style.height =
      size + "px";

    ctx.setTransform(
      dpr,
      0,
      0,
      dpr,
      0,
      0
    );
  }


  function draw(now) {

    const size =
      Math.min(width, height);

    const cx =
      size / 2;

    const cy =
      size / 2;

    const radius =
      size * .495;


    ctx.clearRect(
      0,
      0,
      width,
      height
    );


    /*
     * Base spherical shading.
     */
    const sphere =
      ctx.createRadialGradient(
        cx - radius * .30,
        cy - radius * .32,
        radius * .04,

        cx,
        cy,
        radius * 1.05
      );

    sphere.addColorStop(
      0,
      "#d8dce1"
    );

    sphere.addColorStop(
      .34,
      "#a1a7ae"
    );

    sphere.addColorStop(
      .68,
      "#666e78"
    );

    sphere.addColorStop(
      .88,
      "#343c47"
    );

    sphere.addColorStop(
      1,
      "#0d131c"
    );


    ctx.beginPath();

    ctx.arc(
      cx,
      cy,
      radius,
      0,
      Math.PI * 2
    );

    ctx.fillStyle =
      sphere;

    ctx.fill();


    /*
     * Rotating lunar terrain.
     */
    ctx.save();

    ctx.beginPath();

    ctx.arc(
      cx,
      cy,
      radius * .995,
      0,
      Math.PI * 2
    );

    ctx.clip();


    for (const crater of craters) {

      const longitude =
        crater.longitude +
        rotation;

      /*
       * Project longitude onto
       * visible spherical hemisphere.
       */
      const x =
        Math.sin(longitude) *
        Math.cos(crater.latitude);

      const z =
        Math.cos(longitude) *
        Math.cos(crater.latitude);

      /*
       * Don't draw the far side.
       */
      if (z < -0.05) continue;


      const y =
        Math.sin(crater.latitude);


      const px =
        cx + x * radius * .94;

      const py =
        cy - y * radius * .94;


      const perspective =
        .72 + z * .28;

      const craterRadius =
        radius *
        crater.radius *
        perspective;


      const gradient =
        ctx.createRadialGradient(
          px - craterRadius * .25,
          py - craterRadius * .25,
          craterRadius * .05,

          px,
          py,
          craterRadius
        );


      gradient.addColorStop(
        0,
        `rgba(225,229,234,${.08 * crater.depth})`
      );

      gradient.addColorStop(
        .45,
        `rgba(55,61,68,${.22 * crater.depth})`
      );

      gradient.addColorStop(
        .78,
        `rgba(20,25,31,${.34 * crater.depth})`
      );

      gradient.addColorStop(
        1,
        "rgba(0,0,0,0)"
      );


      ctx.fillStyle =
        gradient;

      ctx.beginPath();

      ctx.arc(
        px,
        py,
        craterRadius,
        0,
        Math.PI * 2
      );

      ctx.fill();


      /*
       * Small crater rim.
       */
      ctx.strokeStyle =
        `rgba(220,225,230,${.08 * crater.depth})`;

      ctx.lineWidth =
        Math.max(
          .5,
          craterRadius * .055
        );

      ctx.beginPath();

      ctx.arc(
        px - craterRadius * .10,
        py - craterRadius * .10,
        craterRadius * .68,
        0,
        Math.PI * 2
      );

      ctx.stroke();
    }

    ctx.restore();


    /*
     * Fine spherical grain.
     */
    const grain =
      ctx.createRadialGradient(
        cx - radius * .18,
        cy - radius * .20,
        radius * .05,
        cx,
        cy,
        radius
      );

    grain.addColorStop(
      0,
      "rgba(255,255,255,.035)"
    );

    grain.addColorStop(
      .55,
      "rgba(255,255,255,.01)"
    );

    grain.addColorStop(
      1,
      "rgba(0,0,0,.08)"
    );

    ctx.beginPath();

    ctx.arc(
      cx,
      cy,
      radius,
      0,
      Math.PI * 2
    );

    ctx.fillStyle =
      grain;

    ctx.fill();


    /*
     * Very slow rotation.
     */
    rotation += .00075;


    requestAnimationFrame(draw);
  }


  resize();

  window.addEventListener(
    "resize",
    resize,
    { passive: true }
  );

  requestAnimationFrame(draw);
}


/*
 * Start on initial page load.
 */
document.addEventListener(
  "DOMContentLoaded",
  () => {
    initProceduralMoon();
  }
);
