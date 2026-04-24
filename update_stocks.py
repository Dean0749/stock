// 修改原本載入資料的邏輯
async function loadStocks() {
  try {
    const response = await fetch('./data/picks.json');
    const data = await response.json();
    
    // 渲染到網頁上的清單 (假設容器 ID 是 list-container)
    const listHtml = data.picks.map(item => `
      <div class="card">
        <div class="row">
          <span class="badge b-blue">${item.ticker}</span>
          <span class="stock-name">${item.name}</span>
          <span class="category-label">${item.category}</span>
        </div>
        <div class="summary-text">${item.reason}</div>
      </div>
    `).join('');
    
    document.getElementById('list-container').innerHTML = listHtml;
  } catch (e) {
    console.error("無法載入股票清單", e);
  }
}

// 頁面加載時執行
window.onload = loadStocks;
