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
   LUNARMATCH — TRUE 3D LUNAR SPHERE
   ========================================================= */

let lunarThreeModule = null;
let lunarSceneInstance = null;

async function loadLunarThree() {
  if (lunarThreeModule) return lunarThreeModule;

  lunarThreeModule = await import(
    "https://cdn.jsdelivr.net/npm/three@0.186.0/build/three.module.js"
  );

  return lunarThreeModule;
}


function createLunarTexture(THREE) {

  const width = 1024;
  const height = 512;

  const canvas = document.createElement("canvas");

  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext("2d");

  /*
   * Base lunar surface.
   */
  const gradient = ctx.createLinearGradient(
    0,
    0,
    width,
    height
  );

  gradient.addColorStop(0, "#aeb5bd");
  gradient.addColorStop(.35, "#737b84");
  gradient.addColorStop(.65, "#969da5");
  gradient.addColorStop(1, "#555d67");

  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);


  /*
   * Fine lunar surface noise.
   */
  const image = ctx.getImageData(
    0,
    0,
    width,
    height
  );

  const data = image.data;

  for (let i = 0; i < data.length; i += 4) {

    const noise =
      (Math.random() - 0.5) * 30;

    data[i] =
      Math.max(0, Math.min(255, data[i] + noise));

    data[i + 1] =
      Math.max(0, Math.min(255, data[i + 1] + noise));

    data[i + 2] =
      Math.max(0, Math.min(255, data[i + 2] + noise));
  }

  ctx.putImageData(image, 0, 0);


  /*
   * Lunar craters.
   */
  const craterCount = 115;

  for (let i = 0; i < craterCount; i++) {

    const x = Math.random() * width;
    const y = Math.random() * height;

    const radius =
      3 + Math.random() * 20;

    const crater =
      ctx.createRadialGradient(
        x - radius * .25,
        y - radius * .25,
        radius * .08,
        x,
        y,
        radius
      );

    crater.addColorStop(
      0,
      "rgba(220,225,230,.28)"
    );

    crater.addColorStop(
      .35,
      "rgba(65,70,76,.18)"
    );

    crater.addColorStop(
      .72,
      "rgba(25,29,34,.32)"
    );

    crater.addColorStop(
      1,
      "rgba(0,0,0,0)"
    );

    ctx.fillStyle = crater;

    ctx.beginPath();
    ctx.arc(
      x,
      y,
      radius,
      0,
      Math.PI * 2
    );
    ctx.fill();


    /*
     * Crater rim.
     */
    ctx.strokeStyle =
      "rgba(220,225,230,.10)";

    ctx.lineWidth =
      Math.max(1, radius * .08);

    ctx.beginPath();

    ctx.arc(
      x - radius * .08,
      y - radius * .08,
      radius * .72,
      0,
      Math.PI * 2
    );

    ctx.stroke();
  }


  /*
   * Larger maria / dark lunar regions.
   */
  for (let i = 0; i < 18; i++) {

    const x = Math.random() * width;
    const y = Math.random() * height;

    const rx = 25 + Math.random() * 75;
    const ry = 12 + Math.random() * 45;

    ctx.save();

    ctx.translate(x, y);

    ctx.rotate(
      Math.random() * Math.PI
    );

    const maria =
      ctx.createRadialGradient(
        0,
        0,
        0,
        0,
        0,
        rx
      );

    maria.addColorStop(
      0,
      "rgba(35,39,44,.25)"
    );

    maria.addColorStop(
      1,
      "rgba(35,39,44,0)"
    );

    ctx.fillStyle = maria;

    ctx.beginPath();

    ctx.ellipse(
      0,
      0,
      rx,
      ry,
      0,
      0,
      Math.PI * 2
    );

    ctx.fill();

    ctx.restore();
  }


  const texture =
    new THREE.CanvasTexture(canvas);

  texture.colorSpace =
    THREE.SRGBColorSpace;

  texture.anisotropy = 4;

  return texture;
}


async function initLunar3D() {

  const canvas =
    document.querySelector("#lunar-canvas");

  if (!canvas) return;

  /*
   * Don't create another renderer when
   * navigating back to Home.
   */
  if (canvas.dataset.lunarReady === "true") {
    return;
  }

  canvas.dataset.lunarReady = "true";

  try {

    const THREE =
      await loadLunarThree();


    const container =
      canvas.parentElement;


    /*
     * Scene
     */
    const scene =
      new THREE.Scene();


    /*
     * Camera
     */
    const camera =
      new THREE.PerspectiveCamera(
        32,
        1,
        0.1,
        100
      );

    camera.position.set(
      0,
      0,
      3.25
    );


    /*
     * Renderer
     */
    const renderer =
      new THREE.WebGLRenderer({
        canvas,
        alpha: true,
        antialias: true,
        powerPreference: "high-performance"
      });

    renderer.setPixelRatio(
      Math.min(window.devicePixelRatio, 2)
    );

    renderer.outputColorSpace =
      THREE.SRGBColorSpace;

    renderer.toneMapping =
      THREE.ACESFilmicToneMapping;

    renderer.toneMappingExposure =
      1.05;


    /*
     * Moon group
     */
    const moonGroup =
      new THREE.Group();

    scene.add(moonGroup);


    /*
     * Actual spherical geometry.
     */
    const geometry =
      new THREE.SphereGeometry(
        1.18,
        128,
        128
      );


    /*
     * Procedural lunar surface.
     */
    const texture =
      createLunarTexture(THREE);


    const material =
      new THREE.MeshStandardMaterial({
        map: texture,

        roughness: 1.0,
        metalness: 0.0,

        bumpMap: texture,
        bumpScale: 0.055
      });


    const moon =
      new THREE.Mesh(
        geometry,
        material
      );

    moonGroup.add(moon);


    /*
     * Main sunlight.
     */
    const keyLight =
      new THREE.DirectionalLight(
        0xe9f1ff,
        3.4
      );

    keyLight.position.set(
      -3,
      1.7,
      4
    );

    scene.add(keyLight);


    /*
     * Soft fill.
     */
    const fillLight =
      new THREE.HemisphereLight(
        0x9fc8ff,
        0x080b12,
        .55
      );

    scene.add(fillLight);


    /*
     * Cool rim light.
     */
    const rimLight =
      new THREE.PointLight(
        0x7ddcff,
        1.15,
        7
      );

    rimLight.position.set(
      2.7,
      .2,
      -2.5
    );

    scene.add(rimLight);


    /*
     * Resize.
     */
    function resize() {

      const width =
        container.clientWidth;

      const height =
        container.clientHeight;

      const size =
        Math.min(width, height);

      renderer.setSize(
        size,
        size,
        false
      );

      camera.aspect = 1;

      camera.updateProjectionMatrix();
    }


    resize();


    /*
     * Slow genuine rotation.
     */
    let lastTime =
      performance.now();

    function animate(now) {

      if (!document.body.contains(canvas)) {
        renderer.dispose();
        texture.dispose();
        geometry.dispose();
        material.dispose();
        return;
      }

      const delta =
        Math.min(
          (now - lastTime) / 1000,
          .05
        );

      lastTime = now;


      /*
       * Full spherical rotation.
       */
      moon.rotation.y +=
        delta * 0.055;


      /*
       * Tiny natural axial movement.
       */
      moon.rotation.x =
        Math.sin(now * 0.00012) * 0.018;


      renderer.render(
        scene,
        camera
      );

      requestAnimationFrame(
        animate
      );
    }

    requestAnimationFrame(
      animate
    );


    /*
     * Responsive resize.
     */
    const observer =
      new ResizeObserver(resize);

    observer.observe(container);

    lunarSceneInstance = {
      renderer,
      observer,
      texture,
      geometry,
      material
    };

  } catch (error) {

    console.error(
      "LUNARMATCH 3D Moon failed:",
      error
    );

    canvas.dataset.lunarReady =
      "false";
  }
}
document.addEventListener(
  "DOMContentLoaded",
  () => {
    initLunar3D();
  }
);
