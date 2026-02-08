fetch("/api/booking/create/", {
  method: "POST",
  body: JSON.stringify({
    object_id: 1,
    name: "Ali",
    phone: "+99890...",
    date_from: "2026-03-20",
    date_to: "2026-03-22"
  })
})
if (booking.status === "approved") {
  showPhone();
}


// 33333333333333333333333333333333333333333333
const tg = window.Telegram.WebApp;
tg.ready();

const API_BASE = "http://127.0.0.1:8000/api";

let selectedObjectId = null;

// Obyektlarni yuklash
fetch(`${API_BASE}/objects/`)
  .then(res => res.json())
  .then(data => renderObjects(data));

function renderObjects(objects) {
  const container = document.getElementById("objects");
  container.innerHTML = "";

  objects.forEach(obj => {
    container.innerHTML += `
      <div class="card">
        <h3>${obj.title}</h3>
        <p>💰 ${obj.price} so‘m</p>
        <p>👥 Sig‘im: ${obj.capacity}</p>
        <button onclick="openModal(${obj.id}, '${obj.title}')">
          📅 Bron qilish
        </button>
      </div>
    `;
  });
}

// Modal ochish
function openModal(id, title) {
  selectedObjectId = id;
  document.getElementById("modalTitle").innerText = title;
  document.getElementById("bookingModal").classList.remove("hidden");
}

// Modal yopish
function closeModal() {
  document.getElementById("bookingModal").classList.add("hidden");
}

// Bron yuborish
document.getElementById("confirmBooking").onclick = () => {
  const name = document.getElementById("clientName").value;
  const phone = document.getElementById("clientPhone").value;

  fetch(`${API_BASE}/booking/create/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      object_id: selectedObjectId,
      name: name,
      phone: phone,
      date_from: document.getElementById("dateFrom").value,
      date_to: document.getElementById("dateTo").value
    })
  })
  .then(res => {
    if (!res.ok) throw new Error("Band");
    return res.json();
  })
  .then(() => {
    alert("✅ Bron yuborildi!");
    closeModal();
  })
  .catch(() => alert("❌ Bu sana band"));
};
