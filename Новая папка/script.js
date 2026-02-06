// Эмодзи для брендов и вкусов
const EMOJI_MAP = {
    // Бренды
    "ЗЛАЯ МОНАШКА": "😈",
    "ANIMMA": "🔥",
    "CATSWILL": "😼",
    "DOTA": "🎮",
    "PODONKI": "👅",
    "САМОУБИЙЦА": "💀",
    "VAPORESSO": "🔋",
    "RICK AND MORTY": "👽",
    
    // Вкусы
    "ВИШНЯ": "🍒", "АРБУЗ": "🍉", "МАЛИНА": "🫐",
    "КЛУБНИКА": "🍓", "АНАНАС": "🍍", "ВИНОГРАД": "🍇",
    "ГРАНАТ": "🧃", "ДЫНЯ": "🍈", "ПЕРСИК": "🍑",
    "ЯБЛОКО": "🍏", "ГРЕЙПФРУТ": "🍊", "ЛЕМОН": "🍋",
    "ЛАЙМ": "🍋", "КЛЮКВА": "🫐", "ЧЕРНИКА": "🫐",
    "ЕЖЕВИКА": "🫐", "СМОРОДИНА": "🫐", "БРУСНИКА": "🫐",
    "АБРИКОС": "🍑", "НЕКТАРИН": "🍑", "СЛИВА": "🟣",
    "КИВИ": "🥝", "АЛОЭ": "🌿", "АЙС": "❄️",
    "ЛЁД": "❄️", "SOUR": "😖", "КИСЛЫЙ": "😖",
    "ЭНЕРГИЯ": "⚡"
};

// Глобальные переменные
let allProducts = [];
let currentBrand = '';

// Telegram Web App
const tg = window.Telegram.WebApp;
tg.expand(); // Развернуть на весь экран

// DOM элементы
const loadingEl = document.getElementById('loading');
const brandsSection = document.getElementById('brands-section');
const productsSection = document.getElementById('products-section');
const brandsList = document.getElementById('brands-list');
const productsList = document.getElementById('products-list');
const brandTitle = document.getElementById('brand-title');
const backBtn = document.getElementById('back-to-brands');
const refreshBtn = document.getElementById('refresh-btn');
const updateTime = document.getElementById('update-time');

// Функции
function getEmoji(text) {
    for (const [key, emoji] of Object.entries(EMOJI_MAP)) {
        if (text.includes(key)) {
            return emoji;
        }
    }
    return '';
}

function formatTasteName(taste, brand) {
    // Убираем название бренда из вкуса если оно есть
    let cleanTaste = taste;
    if (taste.includes(brand)) {
        cleanTaste = taste.replace(brand, '').trim();
    }
    return cleanTaste;
}

// Загрузка данных
async function loadData() {
    try {
        loadingEl.style.display = 'block';
        brandsSection.style.display = 'none';
        productsSection.style.display = 'none';
        
        // Загружаем товары
        const response = await fetch('http://localhost:8080/api/products');
        allProducts = await response.json();
        
        // Обновляем время
        const now = new Date();
        updateTime.textContent = now.toLocaleTimeString('ru-RU');
        
        // Показываем бренды
        showBrands();
        
    } catch (error) {
        console.error('Ошибка загрузки:', error);
        loadingEl.innerHTML = `
            <div style="color: #ff6b6b;">
                ❌ Ошибка загрузки данных
                <button onclick="loadData()" style="margin-top: 20px; padding: 10px 20px; background: #667eea; color: white; border: none; border-radius: 5px;">
                    Попробовать снова
                </button>
            </div>
        `;
    }
}

// Показать бренды
function showBrands() {
    loadingEl.style.display = 'none';
    brandsSection.style.display = 'block';
    productsSection.style.display = 'none';
    
    // Группируем по брендам
    const brands = {};
    allProducts.forEach(product => {
        if (!brands[product.brand]) {
            brands[product.brand] = 0;
        }
        brands[product.brand]++;
    });
    
    // Сортируем по количеству товаров
    const sortedBrands = Object.entries(brands)
        .sort((a, b) => b[1] - a[1]);
    
    // Очищаем список
    brandsList.innerHTML = '';
    
    // Добавляем бренды
    sortedBrands.forEach(([brandName, count]) => {
        const emoji = getEmoji(brandName) || '🏷️';
        const brandCard = document.createElement('div');
        brandCard.className = 'brand-card';
        brandCard.innerHTML = `
            <div class="brand-emoji">${emoji}</div>
            <div class="brand-name">${brandName}</div>
            <div class="brand-count">${count} позиций</div>
        `;
        
        brandCard.addEventListener('click', () => showProductsByBrand(brandName));
        brandsList.appendChild(brandCard);
    });
}

// Показать товары бренда
function showProductsByBrand(brandName) {
    currentBrand = brandName;
    brandsSection.style.display = 'none';
    productsSection.style.display = 'block';
    
    brandTitle.textContent = `${getEmoji(brandName) || '🏷️'} ${brandName}`;
    
    // Фильтруем товары по бренду
    const brandProducts = allProducts.filter(p => p.brand === brandName);
    
    // Очищаем список
    productsList.innerHTML = '';
    
    // Добавляем товары
    brandProducts.forEach(product => {
        const tasteEmoji = getEmoji(product.taste) || '🍃';
        const cleanTaste = formatTasteName(product.taste, brandName);
        
        const productCard = document.createElement('div');
        productCard.className = 'product-card';
        productCard.innerHTML = `
            <div class="product-header">
                <div class="product-taste">${tasteEmoji} ${cleanTaste}</div>
                <div class="product-status">${product.status}</div>
            </div>
            <div class="product-details">
                <span>⚡ ${product.strength}</span>
                <span>📦 ${product.stock} шт.</span>
            </div>
            <div class="product-price">${product.price}</div>
            <button class="order-btn" data-product="${cleanTaste}">
                🛒 Заказать
            </button>
        `;
        
        // Обработчик кнопки заказа
        const orderBtn = productCard.querySelector('.order-btn');
        orderBtn.addEventListener('click', () => {
            orderProduct(cleanTaste, brandName, product.price);
        });
        
        productsList.appendChild(productCard);
    });
}

// Заказ товара
function orderProduct(productName, brand, price) {
    const message = `Заказ: ${brand} - ${productName} (${price})`;
    
    // В Telegram Web App можно открыть чат
    if (tg.platform !== 'unknown') {
        tg.openTelegramLink(`https://t.me/arcsize?text=${encodeURIComponent(message)}`);
    } else {
        // Для браузера
        window.open(`https://t.me/arcsize?text=${encodeURIComponent(message)}`, '_blank');
    }
}

// Назад к брендам
backBtn.addEventListener('click', showBrands);

// Обновить данные
refreshBtn.addEventListener('click', loadData);

// Запуск при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    loadData();
    
    // Если в Telegram, меняем стили
    if (tg.platform !== 'unknown') {
        document.body.style.padding = '0';
        document.querySelector('.container').style.borderRadius = '0';
    }
});