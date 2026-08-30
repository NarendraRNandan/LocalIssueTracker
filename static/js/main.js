// ==========================================================================
// CivicTrack / WorkersHub - Main Client Application Logic
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
  initLanguageSwitcher();
  initCascadingPlaces();
  initViewSwitcher();
  initPublicMap();
  initReportFormAI();
  initPhotoPreview();
});

const languageTranslations = {
  en: {
    navExplore: "Explore Issues",
    navReport: "Report Issue",
    navAdmin: "Admin",
    navWorkerDashboard: "Worker Tasks",
    navAuthorityDashboard: "Authority Dashboard",
    navMyReports: "My Reports",
    navSignOut: "Sign Out",
    navSignIn: "Sign In",
    navWorkerLogin: "Worker Login",
    navCreateAccount: "Create Account",
    notifications: "Notifications",
    searchIssuesPlaceholder: "Search issues, case codes, localities...",
    publicMap: "Public Map",
    submitComplaint: "Submit Complaint",
    officialPortal: "Official Portal",
    backButton: "Back",
  },
  hi: {
    navExplore: "मामले देखें",
    navReport: "मामला दर्ज करें",
    navAdmin: "एडमिन",
    navWorkerDashboard: "कार्यकर्ता कार्य",
    navAuthorityDashboard: "अधिकारी डैशबोर्ड",
    navMyReports: "मेरे रिपोर्ट",
    navSignOut: "साइन आउट",
    navSignIn: "साइन इन",
    navWorkerLogin: "कार्यकर्ता लॉगिन",
    navCreateAccount: "अकाउंट बनाएं",
    notifications: "सूचनाएं",
    searchIssuesPlaceholder: "मामले, केस कोड, स्थान खोजें...",
    publicMap: "सार्वजनिक मानचित्र",
    submitComplaint: "शिकायत दर्ज करें",
    officialPortal: "अधिकारिक पोर्टल",
    backButton: "वापस",
  },
  kn: {
    navExplore: "ಸಮಸ್ಯೆಗಳನ್ನು ವೀಕ್ಷಿಸಿ",
    navReport: "ಸಮಸ್ಯೆ ವರದಿ ಮಾಡಿ",
    navAdmin: "ಆಡ್ಮಿನ್",
    navWorkerDashboard: "ಕೆಲಸಗಾರ ಕಾರ್ಯಗಳು",
    navAuthorityDashboard: "ಅಧಿಕಾರಿಗಳು ಡ್ಯಾಶ್‌ಬೋರ್ಡ್",
    navMyReports: "ನನ್ನ ವರದಿಗಳು",
    navSignOut: "ಸೈನ್ ಔಟ್",
    navSignIn: "ಸೈನ್ ಇನ್",
    navWorkerLogin: "ಕೆಲಸಗಾರ ಲಾಗಿನ್",
    navCreateAccount: "ಖಾತೆ ರಚಿಸಿ",
    notifications: "ಅಧಿಸೂಚನೆಗಳು",
    searchIssuesPlaceholder: "ಸಮಸ್ಯೆಗಳು, केस ಕೋಡ್, ಸ್ಥಳಗಳನ್ನು ಹುಡುಕಿ...",
    publicMap: "ಸರಕಾರಿ ನಕ್ಷೆ",
    submitComplaint: "ಫಿರ್ಯಾದಿ ಸಲ್ಲಿಸಿ",
    officialPortal: "ಅಧಿಕಾರಿಯ ಪೋರ್ಟಲ್",
    backButton: "ಹಿಂದೆ",
  },
};

function initLanguageSwitcher() {
  const langButtons = document.querySelectorAll(".lang-btn");
  const savedLang = localStorage.getItem("civictrack_lang") || "en";

  const applyLanguage = (lang) => {
    const translations = languageTranslations[lang] || languageTranslations.en;
    document.documentElement.lang = lang;

    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.dataset.i18n;
      const defaultText = el.dataset.defaultText || el.textContent.trim();
      el.dataset.defaultText = defaultText;
      el.textContent = translations[key] || defaultText;
    });

    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      const key = el.dataset.i18nPlaceholder;
      const defaultText = el.dataset.defaultPlaceholder || el.getAttribute("placeholder") || "";
      el.dataset.defaultPlaceholder = defaultText;
      el.setAttribute("placeholder", translations[key] || defaultText);
    });

    document.querySelectorAll("[data-i18n-title]").forEach((el) => {
      const key = el.dataset.i18nTitle;
      const defaultText = el.dataset.defaultTitle || el.getAttribute("title") || "";
      el.dataset.defaultTitle = defaultText;
      el.setAttribute("title", translations[key] || defaultText);
    });

    const backBtn = document.querySelector(".floating-back-btn");
    if (backBtn && translations.backButton) {
      backBtn.textContent = `← ${translations.backButton}`;
    }

    langButtons.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.lang === lang);
    });
    localStorage.setItem("civictrack_lang", lang);
  };

  langButtons.forEach((btn) => {
    btn.addEventListener("click", () => applyLanguage(btn.dataset.lang));
  });

  applyLanguage(savedLang);
}

// --------------------------------------------------------------------------
// 1. Cascading Location Dropdowns (State -> District -> City/Town)
// --------------------------------------------------------------------------
function initCascadingPlaces() {
  const stateSelects = document.querySelectorAll(".cascading-state");

  stateSelects.forEach((stateSelect) => {
    const parentContainer = stateSelect.closest(".filter-grid, .report-form, .auth-form-container") || document;
    const districtSelect = parentContainer.querySelector(".cascading-district");
    const citySelect = parentContainer.querySelector(".cascading-city");

    if (!districtSelect) return;

    stateSelect.addEventListener("change", async () => {
      const selectedState = stateSelect.value;
      districtSelect.innerHTML = '<option value="">Loading districts...</option>';
      if (citySelect) citySelect.innerHTML = '<option value="">All Cities / Towns</option>';

      if (!selectedState || selectedState === "all") {
        districtSelect.innerHTML = '<option value="">All Districts</option>';
        return;
      }

      try {
        const res = await fetch(`/api/places/districts?state=${encodeURIComponent(selectedState)}`);
        const data = await res.json();
        districtSelect.innerHTML = '<option value="">Select District</option>';
        data.districts.forEach((d) => {
          const opt = document.createElement("option");
          opt.value = d;
          opt.textContent = d;
          districtSelect.appendChild(opt);
        });
      } catch (err) {
        console.error("Error fetching districts:", err);
        districtSelect.innerHTML = '<option value="">All Districts</option>';
      }
    });

    if (districtSelect && citySelect) {
      districtSelect.addEventListener("change", async () => {
        const selectedState = stateSelect.value;
        const selectedDistrict = districtSelect.value;
        citySelect.innerHTML = '<option value="">Loading cities...</option>';

        if (!selectedDistrict || selectedDistrict === "all") {
          citySelect.innerHTML = '<option value="">All Cities / Towns</option>';
          return;
        }

        try {
          const res = await fetch(
            `/api/places/cities?state=${encodeURIComponent(selectedState)}&district=${encodeURIComponent(selectedDistrict)}`
          );
          const data = await res.json();
          citySelect.innerHTML = '<option value="">Select City / Town</option>';
          data.cities.forEach((c) => {
            const opt = document.createElement("option");
            opt.value = c;
            opt.textContent = c;
            citySelect.appendChild(opt);
          });
        } catch (err) {
          console.error("Error fetching cities:", err);
          citySelect.innerHTML = '<option value="">All Cities / Towns</option>';
        }
      });
    }
  });
}

// --------------------------------------------------------------------------
// 2. View Switcher (Map vs Grid on Homepage)
// --------------------------------------------------------------------------
function initViewSwitcher() {
  const mapBtn = document.getElementById("view-map-btn");
  const gridBtn = document.getElementById("view-grid-btn");
  const mapContainer = document.getElementById("map-container");
  const gridContainer = document.getElementById("grid-container");

  if (!mapBtn || !gridBtn) return;

  const setGridView = () => {
    gridBtn.classList.add("active");
    mapBtn.classList.remove("active");
    if (mapContainer) mapContainer.style.display = "none";
    if (gridContainer) gridContainer.style.display = "grid";
  };

  const setMapView = () => {
    mapBtn.classList.add("active");
    gridBtn.classList.remove("active");
    if (mapContainer) mapContainer.style.display = "block";
    if (gridContainer) gridContainer.style.display = "none";
    if (window.leafletMap) {
      setTimeout(() => window.leafletMap.invalidateSize(), 200);
    }
  };

  mapBtn.addEventListener("click", setMapView);
  gridBtn.addEventListener("click", setGridView);

  setGridView();
}

// --------------------------------------------------------------------------
// 3. Public Leaflet Map (Homepage)
// --------------------------------------------------------------------------
function initPublicMap() {
  const mapDiv = document.getElementById("map-container");
  if (!mapDiv || typeof L === "undefined") return;

  const map = L.map("map-container").setView([12.9716, 77.5946], 6); // Centered on India South/Central
  window.leafletMap = map;

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://openstreetmap.org">OpenStreetMap</a>',
  }).addTo(map);

  // Fetch issue geojson
  const params = new URLSearchParams(window.location.search);
  fetch(`/api/issues?${params.toString()}`)
    .then((res) => res.json())
    .then((geoData) => {
      if (!geoData.features || geoData.features.length === 0) return;

      const markers = [];

      geoData.features.forEach((f) => {
        const [lng, lat] = f.geometry.coordinates;
        const p = f.properties;

        let color = "#3b82f6"; // Reported
        if (p.status === "In Progress") color = "#f59e0b";
        if (p.status === "Resolved") color = "#10b981";
        if (p.priority === "Urgent") color = "#ef4444";

        const markerHtml = `
          <div style="background-color: ${color}; width: 22px; height: 22px; border-radius: 50%; border: 3px solid #ffffff; box-shadow: 0 2px 6px rgba(0,0,0,0.3);"></div>
        `;

        const customIcon = L.divIcon({
          className: "custom-div-icon",
          html: markerHtml,
          iconSize: [22, 22],
          iconAnchor: [11, 11],
        });

        const marker = L.marker([lat, lng], { icon: customIcon }).addTo(map);
        markers.push(marker);

        const popupContent = `
          <div style="font-family: var(--font-sans); min-width: 220px;">
            <div style="font-size: 0.75rem; font-weight: 700; color: #64748b; margin-bottom: 3px;">${p.case_code} &bull; ${p.category}</div>
            <div style="font-size: 0.95rem; font-weight: 700; color: #0f172a; margin-bottom: 6px;">${p.title}</div>
            <div style="font-size: 0.8rem; color: #475569; margin-bottom: 8px;">${p.locality}</div>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 0.75rem; font-weight: 700; color: ${color};">${p.status}</span>
              <a href="/issue/${p.id}" style="font-size: 0.82rem; font-weight: 600; color: #4f46e5;">View Details &rarr;</a>
            </div>
          </div>
        `;

        marker.bindPopup(popupContent);
      });

      if (markers.length > 0) {
        const group = new L.featureGroup(markers);
        map.fitBounds(group.getBounds().pad(0.15));
      }
    })
    .catch((err) => console.error("Error loading map issues:", err));
}

// --------------------------------------------------------------------------
// 4. Report Form AI (Live Category Suggestion & Duplicate Detection)
// --------------------------------------------------------------------------
function initReportFormAI() {
  const titleInput = document.getElementById("report-title");
  const descInput = document.getElementById("report-desc");
  const categorySelect = document.getElementById("report-category");
  const prioritySelect = document.getElementById("report-priority");
  const aiBox = document.getElementById("ai-suggestion-box");
  const aiCatText = document.getElementById("ai-suggested-category");
  const aiPrioText = document.getElementById("ai-suggested-priority");
  const aiApplyBtn = document.getElementById("ai-apply-btn");
  const duplicateContainer = document.getElementById("duplicate-results-container");

  if (!titleInput || !descInput) return;

  let debounceTimer = null;

  const triggerAI = () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(async () => {
      const title = titleInput.value.trim();
      const desc = descInput.value.trim();
      if ((title + " " + desc).length < 5) {
        if (aiBox) aiBox.style.display = "none";
        return;
      }

      // 1. Suggest Category & Priority
      try {
        const res = await fetch("/api/ai/suggest-category", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, description: desc }),
        });
        const data = await res.json();

        if (aiBox && data.category) {
          aiBox.style.display = "flex";
          aiCatText.textContent = `${data.category} (${Math.round(data.confidence * 100)}% match)`;
          aiPrioText.textContent = `${data.priority}`;

          if (aiApplyBtn) {
            aiApplyBtn.onclick = () => {
              if (categorySelect) categorySelect.value = data.category;
              if (prioritySelect) prioritySelect.value = data.priority;
              aiBox.style.display = "none";
            };
          }
        }
      } catch (err) {
        console.error("AI suggestion error:", err);
      }

      // 2. Check Duplicates
      const state = document.getElementById("report-state")?.value || "";
      const district = document.getElementById("report-district")?.value || "";
      const city_town = document.getElementById("report-city")?.value || "";

      try {
        const dupRes = await fetch("/api/ai/check-duplicates", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, description: desc, state, district, city_town }),
        });
        const dupData = await dupRes.json();

        if (duplicateContainer) {
          if (dupData.duplicates && dupData.duplicates.length > 0) {
            duplicateContainer.style.display = "block";
            let html = `
              <div class="duplicate-alert-box">
                <div style="display: flex; align-items: center; gap: 0.5rem; color: #92400e; font-weight: 700; font-size: 0.92rem;">
                  <span>⚠️ Potential Duplicate Issues Found Nearby</span>
                </div>
                <div style="font-size: 0.84rem; color: #78350f; margin-top: 0.2rem;">
                  A similar issue has already been reported in this area. You can upvote it to increase priority instead of creating a duplicate.
                </div>
            `;
            dupData.duplicates.forEach((d) => {
              html += `
                <div class="duplicate-item">
                  <div>
                    <strong style="font-size: 0.88rem; color: #0f172a;">${d.case_code}: ${d.title}</strong>
                    <div style="font-size: 0.78rem; color: #64748b;">${d.category} &bull; ${d.locality} &bull; <strong>${d.similarity_score}% similarity</strong></div>
                  </div>
                  <a href="/issue/${d.id}" target="_blank" class="btn btn-sm btn-primary" style="white-space: nowrap;">
                    View & Upvote (${d.upvotes})
                  </a>
                </div>
              `;
            });
            html += `</div>`;
            duplicateContainer.innerHTML = html;
          } else {
            duplicateContainer.style.display = "none";
          }
        }
      } catch (err) {
        console.error("Duplicate check error:", err);
      }
    }, 400);
  };

  titleInput.addEventListener("input", triggerAI);
  descInput.addEventListener("input", triggerAI);

  // Initialize interactive map for report page
  initReportPinMap();
}

// --------------------------------------------------------------------------
// 5. Interactive Pin Map for Report Form
// --------------------------------------------------------------------------
function initReportPinMap() {
  const mapDiv = document.getElementById("report-map");
  if (!mapDiv || typeof L === "undefined") return;

  const latInput = document.getElementById("report-lat");
  const lngInput = document.getElementById("report-lng");
  const gpsBtn = document.getElementById("btn-gps-location");
  const stateSelect = document.getElementById("report-state");
  const districtSelect = document.getElementById("report-district");
  const citySelect = document.getElementById("report-city");
  const localityInput = document.querySelector('input[name="locality_address"]');

  let defaultLat = 12.2958;
  let defaultLng = 76.6394;

  const map = L.map("report-map").setView([defaultLat, defaultLng], 12);
  window.reportLeafletMap = map;
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(map);

  let marker = L.marker([defaultLat, defaultLng], { draggable: true }).addTo(map);
  window.reportMarker = marker;

  const updateCoords = (lat, lng) => {
    if (latInput) latInput.value = lat.toFixed(6);
    if (lngInput) lngInput.value = lng.toFixed(6);
  };

  const autoFillLocationFromLatLng = async (lat, lng) => {
    try {
      const response = await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}`);
      const data = await response.json();
      const address = data.address || {};
      const stateName = address.state || address.region || "";
      const districtName = address.county || address.district || address.city_district || "";
      const cityName = address.city || address.town || address.village || address.municipality || address.suburb || "";
      const localityName = address.road || address.neighbourhood || address.hamlet || "";

      if (stateName && stateSelect) {
        const stateExists = [...stateSelect.options].some((option) => option.value === stateName);
        if (stateExists) stateSelect.value = stateName;
        if (stateSelect.value) {
          stateSelect.dispatchEvent(new Event("change"));
        }
      }

      setTimeout(() => {
        if (districtName && districtSelect) {
          const districtExists = [...districtSelect.options].some((option) => option.value === districtName);
          if (districtExists) districtSelect.value = districtName;
          if (districtSelect.value) {
            districtSelect.dispatchEvent(new Event("change"));
          }
        }
        setTimeout(() => {
          if (cityName && citySelect) {
            const cityExists = [...citySelect.options].some((option) => option.value === cityName);
            if (cityExists) citySelect.value = cityName;
          }
          if (localityName && localityInput) {
            if (!localityInput.value.trim()) localityInput.value = localityName;
          }
        }, 250);
      }, 350);
    } catch (err) {
      console.warn("Location reverse geocode failed:", err);
    }
  };

  updateCoords(defaultLat, defaultLng);

  marker.on("dragend", (e) => {
    const pos = marker.getLatLng();
    updateCoords(pos.lat, pos.lng);
    autoFillLocationFromLatLng(pos.lat, pos.lng);
  });

  map.on("click", (e) => {
    marker.setLatLng(e.latlng);
    updateCoords(e.latlng.lat, e.latlng.lng);
    autoFillLocationFromLatLng(e.latlng.lat, e.latlng.lng);
  });

  if (gpsBtn && navigator.geolocation) {
    gpsBtn.addEventListener("click", () => {
      gpsBtn.textContent = "📍 Detecting GPS...";
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const { latitude, longitude } = pos.coords;
          map.setView([latitude, longitude], 15);
          marker.setLatLng([latitude, longitude]);
          updateCoords(latitude, longitude);
          autoFillLocationFromLatLng(latitude, longitude);
          gpsBtn.textContent = "📍 GPS Location Found!";
          setTimeout(() => (gpsBtn.textContent = "📍 Use My GPS Location"), 3000);
        },
        (err) => {
          alert("Could not detect GPS location. Please click on the map manually to drop the pin.");
          gpsBtn.textContent = "📍 Use My GPS Location";
        }
      );
    });
  }
}

// --------------------------------------------------------------------------
// 6. Photo Drag & Drop Preview
// --------------------------------------------------------------------------
function initPhotoPreview() {
  const photoInputs = document.querySelectorAll('input[type="file"][accept*="image"]');
  photoInputs.forEach((input) => {
    input.addEventListener("change", () => {
      const file = input.files[0];
      const previewContainer = input.parentElement.querySelector(".photo-preview-target");
      if (file && previewContainer) {
        const reader = new FileReader();
        reader.onload = (e) => {
          previewContainer.innerHTML = `
            <img src="${e.target.result}" style="max-height: 160px; border-radius: 8px; margin-top: 8px; border: 1px solid #cbd5e1; object-fit: cover;">
          `;
        };
        reader.readAsDataURL(file);
      }
    });
  });
}

