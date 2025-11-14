# Селекторы и локаторы для Telegram Web (web.telegram.org/k)

**Дата анализа:** 2024-11-15
**Источник:** HTML файлы из `/tg-automatizamtion/htmls/`
**Файлы:**
- `main.html` - главная страница с поиском
- `search.html` - страница с результатами поиска
- `chat.html` - открытый чат с полем для ввода сообщения

---

## 📋 Содержание

1. [Поиск чата](#1-поиск-чата-chat-search)
2. [Результаты поиска](#2-результаты-поиска-search-results)
3. [Открытие чата](#3-открытие-чата-opening-chat)
4. [Отправка сообщения](#4-отправка-сообщения-sending-messages)
5. [Индикаторы статуса](#5-индикаторы-статуса-отправки-send-status-indicators)
6. [Обработка ошибок](#6-обработка-ошибок-и-ограничений-error-handling)
7. [Дополнительные селекторы](#7-дополнительные-важные-селекторы-additional-important-selectors)
8. [Рейтинг надежности](#8-селекторы-по-надежности-selectors-ranked-by-reliability)
9. [Timing considerations](#9-важные-timing-considerations-timing-considerations)
10. [Стратегии автоматизации](#10-рекомендуемые-стратегии-автоматизации-recommended-automation-strategies)

---

## 1. ПОИСК ЧАТА (Chat Search)

### 1.1. Поле поиска (Search Input Field)

**CSS Selector:**
```css
.input-search-input
input.input-field-input.input-search-input
```

**XPath:**
```xpath
//input[@class='input-field-input is-empty input-search-input with-focus-effect']
//input[contains(@class, 'input-search-input')]
```

**HTML Structure:**
```html
<input type="text"
       class="input-field-input is-empty input-search-input with-focus-effect"
       autocomplete="off"
       dir="auto"
       placeholder=" ">
```

**Атрибуты:**
- `type="text"`
- `autocomplete="off"`
- `dir="auto"`
- `placeholder=" "` (пустой, текст показывается через отдельный элемент)

**Классы:**
- `input-field-input` - базовый класс поля ввода
- `input-search-input` - специфичный класс поиска
- `with-focus-effect` - эффект при фокусе
- `is-empty` - когда поле пустое (динамический класс)

**Родительский контейнер:**
```css
.input-search
.sidebar-header.main-search-sidebar-header
```

**Надежность:** ⭐⭐⭐⭐⭐ (очень высокая)
**Timing:** Доступен сразу после загрузки страницы

---

### 1.2. Placeholder текст

**CSS Selector:**
```css
.input-search-placeholder
span.i18n.input-search-placeholder.will-animate
```

**Text Content:** `"Search"`

**Классы:**
- `i18n` - интернационализация
- `input-search-placeholder` - специфичный класс
- `will-animate` - анимация

**Надежность:** ⭐⭐⭐ (средняя - декоративный элемент)

---

### 1.3. Кнопка очистить поиск (Clear Search Button)

**CSS Selector:**
```css
.input-search-clear
button.btn-icon.input-search-clear
```

**XPath:**
```xpath
//button[contains(@class, 'input-search-clear')]
```

**HTML Structure:**
```html
<button class="btn-icon input-search-clear input-search-part input-search-button"
        cancel-mouse-down="">
    <span class="tgico button-icon"></span>
</button>
```

**Атрибуты:**
- `cancel-mouse-down=""` - отмена события mousedown

**Классы:**
- `btn-icon` - базовый класс кнопки-иконки
- `input-search-clear` - специфичный класс
- `input-search-part` - часть поиска
- `input-search-button` - кнопка поиска

**Надежность:** ⭐⭐⭐⭐⭐ (очень высокая)
**Timing:** Появляется только когда в поле поиска есть текст

---

### 1.4. Иконка поиска (Search Icon)

**CSS Selector:**
```css
.input-search-icon
span.tgico.input-search-part.input-search-icon
```

**Классы:**
- `tgico` - Telegram иконка
- `input-search-part` - часть поиска
- `input-search-icon` - иконка поиска
- `will-animate` - анимация

**Надежность:** ⭐⭐ (низкая - декоративный элемент)

---

## 2. РЕЗУЛЬТАТЫ ПОИСКА (Search Results)

### 2.1. Список результатов (Chat List)

**CSS Selector:**
```css
.chatlist
ul.chatlist.virtual-chatlist
```

**XPath:**
```xpath
//ul[@class='chatlist virtual-chatlist']
```

**HTML Structure:**
```html
<ul class="chatlist virtual-chatlist" data-autonomous="0">
    <!-- Chat items here -->
</ul>
```

**Атрибуты:**
- `data-autonomous="0"` - виртуализация списка

**Родительский контейнер:**
```css
.chatlist-top
```

**Надежность:** ⭐⭐⭐⭐ (высокая)

---

### 2.2. Отдельный элемент чата (Individual Chat Item)

**CSS Selector (РЕКОМЕНДУЕТСЯ):**
```css
.chatlist-chat
a.chatlist-chat[data-peer-id]
```

**XPath (РЕКОМЕНДУЕТСЯ):**
```xpath
//a[contains(@class, 'chatlist-chat')]
//a[@data-peer-id]
```

**HTML Structure:**
```html
<a class="row no-wrap row-with-padding row-clickable hover-effect rp chatlist-chat chatlist-chat-bigger row-big"
   href="#-1881876712"
   data-peer-id="-1881876712">
    <!-- Chat content -->
</a>
```

**Ключевые атрибуты:**
- `href` - например, `"#-1881876712"` (peer ID)
- `data-peer-id` - например, `"-1881876712"` ⭐ **САМЫЙ НАДЕЖНЫЙ ИДЕНТИФИКАТОР**

**Классы:**
- `row` - базовый класс строки
- `no-wrap` - без переноса
- `row-with-padding` - с отступами
- `row-clickable` - кликабельная
- `hover-effect` - эффект при наведении
- `rp` - (?)
- `chatlist-chat` - специфичный класс чата
- `chatlist-chat-bigger` - увеличенный вариант
- `row-big` - большая строка

**Условные классы:**
- `is-muted` - если чат в режиме без звука
- `_Item_5idej_1` - виртуальный список (ДИНАМИЧЕСКИЙ - НЕ ИСПОЛЬЗОВАТЬ)

**Надежность:** ⭐⭐⭐⭐⭐ (очень высокая - благодаря `data-peer-id`)

---

### 2.3. Название чата в результатах (Chat Title)

**CSS Selector:**
```css
.peer-title
span.peer-title[data-peer-id]
```

**XPath:**
```xpath
//a[@class='chatlist-chat']//span[@class='peer-title']
```

**HTML Structure:**
```html
<span class="peer-title"
      dir="auto"
      data-peer-id="-1881876712"
      data-from-name="0"
      data-dialog="1"
      data-only-first-name="0"
      data-with-icons="1"
      data-thread-id="0"
      data-icons-color="primary-color"
      data-me-as-notes="0"
      data-as-all-chats="0">
    Авито Чат|Отзывы| Работа
</span>
```

**Атрибуты:**
- `dir="auto"` - направление текста
- `data-peer-id` - идентификатор чата
- `data-from-name="0"` - (?)
- `data-dialog="1"` - это диалог
- `data-only-first-name="0"` - показывать полное имя
- `data-with-icons="1"` - с иконками
- `data-thread-id="0"` - ID треда
- `data-icons-color="primary-color"` - цвет иконок
- `data-me-as-notes="0"` - (?)
- `data-as-all-chats="0"` - (?)

**Text Content:** Название чата/группы

**Надежность:** ⭐⭐⭐⭐⭐ (очень высокая)

---

### 2.4. Subtitle/последнее сообщение (Last Message Preview)

**CSS Selector:**
```css
.dialog-subtitle
.dialog-subtitle-span
.row-subtitle.no-wrap.dialog-subtitle-flex
```

**Классы:**
- `dialog-subtitle-span` - текст subtitle
- `dialog-subtitle-span-overflow` - с overflow
- `dialog-subtitle-span-last` - последний элемент

**Надежность:** ⭐⭐⭐ (средняя)

---

### 2.5. Аватар чата (Chat Avatar)

**CSS Selector:**
```css
.dialog-avatar
.avatar.dialog-avatar
```

**HTML Structure:**
```html
<div class="avatar avatar-like avatar-54 avatar-gradient dialog-avatar row-media row-media-bigger"
     data-peer-id="-1881876712"
     data-color="violet">
    <!-- Avatar content -->
</div>
```

**Атрибуты:**
- `data-peer-id` - идентификатор чата
- `data-color` - цвет аватара (violet, pink, green, и т.д.)

**Классы:**
- `avatar` - базовый класс
- `avatar-like` - стиль аватара
- `avatar-54` - размер (54px)
- `avatar-gradient` - градиент
- `dialog-avatar` - аватар диалога
- `row-media` - медиа в строке
- `row-media-bigger` - увеличенный размер

**Надежность:** ⭐⭐⭐⭐ (высокая)

---

### 2.6. Количество непрочитанных (Unread Badge)

**CSS Selector:**
```css
.badge.unread
.dialog-subtitle-badge.badge.badge-22.dialog-subtitle-badge-unread.is-visible.unread
```

**Visibility:** Имеет класс `is-visible` когда есть непрочитанные сообщения

**Надежность:** ⭐⭐⭐ (средняя)

---

## 3. ОТКРЫТИЕ ЧАТА (Opening Chat)

### 3.1. Индикатор открытого чата - Topbar

**CSS Selector:**
```css
.topbar
.sidebar-header.topbar
```

**HTML Structure:**
```html
<div class="sidebar-header topbar has-avatar is-pinned-message-shown"
     data-floating="0">
    <!-- Topbar content -->
</div>
```

**Атрибуты:**
- `data-floating="0"` - не плавающий

**Классы:**
- `sidebar-header` - заголовок сайдбара
- `topbar` - верхняя панель
- `has-avatar` - есть аватар
- `is-pinned-message-shown` - показано закрепленное сообщение (условный)

**Надежность:** ⭐⭐⭐⭐⭐ (очень высокая - индикатор открытого чата)
**Timing:** Появляется сразу после открытия чата

---

### 3.2. Информация о чате (Chat Info Container)

**CSS Selector:**
```css
.chat-info
.chat-info-container
```

**XPath:**
```xpath
//div[@class='chat-info']
```

**Надежность:** ⭐⭐⭐⭐ (высокая)

---

### 3.3. Название чата в header (Chat Title in Header)

**CSS Selector:**
```css
.chat-info .peer-title
span.peer-title[data-dialog="1"]
```

**XPath:**
```xpath
//div[@class='chat-info']//span[@class='peer-title']
```

**HTML Structure:**
```html
<span class="peer-title"
      dir="auto"
      data-peer-id="-1845767513"
      data-dialog="1"
      data-with-icons="1"
      data-thread-id="0"
      data-me-as-notes="0">
    Авито Чат|Отзывы| Работа
</span>
```

**Атрибуты:**
- `dir="auto"` - направление текста
- `data-peer-id` - идентификатор чата (⭐ ВАЖНО)
- `data-dialog="1"` - это диалог
- `data-with-icons="1"` - с иконками
- `data-thread-id="0"` - ID треда
- `data-me-as-notes="0"` - (?)

**Text Content:** Название чата/группы

**Надежность:** ⭐⭐⭐⭐⭐ (очень высокая)

---

### 3.4. Информация о членах группы (Members Info)

**CSS Selector:**
```css
.chat-info .info
```

**Text Content:** Например, `"7 442 members, 223 online"`

**Классы:**
- `i18n` - интернационализация

**Надежность:** ⭐⭐⭐ (средняя)

---

### 3.5. Кнопка назад/закрыть чат (Back Button)

**CSS Selector:**
```css
.sidebar-close-button
button.btn-icon.sidebar-close-button
```

**HTML Structure:**
```html
<button class="btn-icon sidebar-close-button">
    <span class="tgico button-icon"></span>
</button>
```

**Надежность:** ⭐⭐⭐⭐ (высокая)

---

## 4. ОТПРАВКА СООБЩЕНИЯ (Sending Messages)

### 4.1. Контейнер ввода сообщения (Message Input Container)

**CSS Selector:**
```css
.input-message-container
```

**Родитель:**
```css
.new-message-wrapper
```

**Надежность:** ⭐⭐⭐⭐ (высокая)

---

### 4.2. Поле ввода сообщения (Message Input Field) ⭐ ВАЖНО

**CSS Selector (РЕКОМЕНДУЕТСЯ):**
```css
.input-message-input[contenteditable="true"]
div.input-message-input.scrollable.scrollable-y.no-scrollbar[contenteditable="true"]
```

**XPath (РЕКОМЕНДУЕТСЯ):**
```xpath
//div[@class='input-message-input scrollable scrollable-y no-scrollbar' and @contenteditable='true']
//div[@contenteditable='true' and contains(@class, 'input-message-input')]
```

**HTML Structure:**
```html
<div class="input-message-input scrollable scrollable-y no-scrollbar"
     contenteditable="true"
     dir="auto"
     tabindex="-1"
     data-peer-id="-1845767513"
     style="...">
</div>
```

**Атрибуты (КЛЮЧЕВЫЕ):**
- `contenteditable="true"` ⭐ - редактируемый div
- `data-peer-id="-1845767513"` ⭐ - идентификатор чата (ВАЖНО для проверки)
- `dir="auto"` - направление текста
- `tabindex="-1"` - не в порядке табуляции
- `style` - динамическая высота

**Классы:**
- `input-message-input` - специфичный класс
- `scrollable` - прокручиваемый
- `scrollable-y` - вертикальная прокрутка
- `no-scrollbar` - без видимого скроллбара
- `is-empty` - когда пустое (динамический класс)

**Надежность:** ⭐⭐⭐⭐⭐ (очень высокая)
**Timing:** Доступен когда чат открыт и есть возможность писать

**ВАЖНО:** Это `contenteditable` div, а не `<textarea>` или `<input>`!

---

### 4.3. Placeholder для ввода

**CSS Selector:**
```css
.input-field-placeholder
span.input-field-placeholder.i18n
```

**Text Content:** `"Message"`

**Надежность:** ⭐⭐ (низкая - декоративный элемент)

---

### 4.4. Fake input (технический элемент)

**CSS Selector:**
```css
.input-message-input.input-field-input-fake
```

**HTML Structure:**
```html
<div class="input-message-input is-empty scrollable scrollable-y no-scrollbar input-field-input-fake"
     contenteditable="true"
     tabindex="-1">
</div>
```

**Примечание:** Используется для технических целей, НЕ для прямого взаимодействия

**Надежность:** ⭐ (не использовать для автоматизации)

---

### 4.5. Кнопка отправки (Send Button) ⭐ ВАЖНО

**CSS Selector (РЕКОМЕНДУЕТСЯ):**
```css
.btn-send
button.btn-send
```

**XPath:**
```xpath
//button[contains(@class, 'btn-send')]
```

**HTML Structure:**
```html
<button class="btn-icon rp btn-circle btn-send animated-button-icon send"
        tabindex="-1">
    <!-- Icons for different states -->
</button>
```

**Атрибуты:**
- `tabindex="-1"` - не в порядке табуляции

**Классы:**
- `btn-icon` - кнопка-иконка
- `rp` - (?)
- `btn-circle` - круглая кнопка
- `btn-send` - кнопка отправки
- `animated-button-icon` - анимированная иконка
- `send` - состояние отправки

**Дочерние элементы (иконки для разных состояний):**
```html
<span class="tgico animated-button-icon-icon btn-send-icon-send"></span>
<span class="tgico animated-button-icon-icon btn-send-icon-schedule"></span>
<span class="tgico animated-button-icon-icon btn-send-icon-edit"></span>
<span class="tgico animated-button-icon-icon btn-send-icon-record"></span>
<span class="tgico animated-button-icon-icon btn-send-icon-forward"></span>
```

**Надежность:** ⭐⭐⭐⭐⭐ (очень высокая)
**Timing:** Видима когда в поле ввода есть текст ИЛИ доступна запись голоса

---

### 4.6. Меню отправки (Send Menu)

**CSS Selector:**
```css
.menu-send
.btn-menu.menu-send
```

**Classes:**
```css
.btn-menu.menu-send.top-left
```

**Опции меню:**
- "Send Without Sound"
- "Schedule Message"
- "Set a Reminder"
- "Send When Online"
- "Remove Effect"

**Надежность:** ⭐⭐⭐ (средняя)

---

### 4.7. Контейнер кнопки отправки

**CSS Selector:**
```css
.btn-send-container
```

**Надежность:** ⭐⭐⭐⭐ (высокая)

---

### 4.8. Кнопка эмодзи (Emoji Button)

**CSS Selector:**
```css
.toggle-emoticons
button.btn-icon.toggle-emoticons
```

**XPath:**
```xpath
//button[@class='btn-icon toggle-emoticons']
```

**Надежность:** ⭐⭐⭐⭐ (высокая)

---

### 4.9. Кнопка прикрепления файлов (Attach File Button)

**CSS Selector:**
```css
.attach-file
.btn-icon.btn-menu-toggle.attach-file
```

**HTML Structure:**
```html
<button class="btn-icon btn-menu-toggle attach-file">
    <span class="tgico"></span>
</button>
```

**Надежность:** ⭐⭐⭐⭐ (высокая)

---

## 5. ИНДИКАТОРЫ СТАТУСА ОТПРАВКИ (Send Status Indicators)

### 5.1. Статус отправки сообщения (Message Sending Status)

**CSS Selector:**
```css
.sending-status
.message-status.sending-status
```

**HTML Structure:**
```html
<span class="message-status sending-status">
    <!-- Status icon -->
</span>
```

**Состояния:**
- С классом `.hide` - не видим
- Без `.hide` - видим

**Надежность:** ⭐⭐⭐ (средняя - часто меняется)

---

### 5.2. Иконки статуса

**Single Check (Sent):**
```css
.sending-status-icon-check
```

**Double Checks (Delivered):**
```css
.sending-status-icon-checks
span.tgico.sending-status-icon.sending-status-icon-checks
```

**Надежность:** ⭐⭐⭐ (средняя)

---

### 5.3. Время сообщения (Message Time)

**CSS Selector:**
```css
.message-time
span.message-time
```

**HTML Structure:**
```html
<span class="message-time">
    <span class="i18n" dir="auto">13:57</span>
</span>
```

**Надежность:** ⭐⭐⭐ (средняя)

---

## 6. ОБРАБОТКА ОШИБОК И ОГРАНИЧЕНИЙ (Error Handling)

### 6.1. Индикатор "No Results" (когда чат не найден)

**Примечание:** В предоставленных HTML файлах не найдено явного элемента "No results".

**Возможные стратегии обнаружения:**
```css
/* Проверить что список пуст */
ul.chatlist:empty

/* Или нет элементов чата */
ul.chatlist:not(:has(.chatlist-chat))
```

**Python (Playwright):**
```python
# Ждем результатов или timeout
try:
    await page.wait_for_selector('.chatlist-chat', timeout=5000)
    chat_found = True
except TimeoutError:
    chat_found = False  # No results
```

**Надежность:** ⭐⭐⭐⭐ (высокая - через отсутствие элементов)

---

### 6.2. Блокировка отправки - кнопки контроля (Chat Input Control Buttons)

**CSS Selector:**
```css
.chat-input-control-button
button.btn-primary.btn-transparent.text-bold.chat-input-control-button.rp
```

**HTML Structure:**
```html
<button class="btn-primary btn-transparent text-bold chat-input-control-button rp">
    <span class="i18n">BUTTON_TEXT</span>
</button>
```

**Возможные тексты кнопок (разные состояния):**
1. **"START"** - для ботов
2. **"Unblock"** - когда пользователь заблокирован
3. **"JOIN"** - когда нужно вступить в канал
4. **"Only Premium users can message..."** - требуется Premium
5. **"Open Chat"** - когда чат недоступен

**Классы состояния:**
- `.hide` - кнопка не релевантна для текущего состояния (скрыта)

**Надежность:** ⭐⭐⭐⭐⭐ (очень высокая - явный индикатор ограничений)

**Проверка:**
```python
# Проверить видима ли кнопка JOIN
join_button = page.locator('button.chat-input-control-button:has-text("JOIN"):not(.hide)')
if await join_button.count() > 0:
    # Нужно вступить в канал
    pass
```

---

### 6.3. Frozen Account Indicator (Аккаунт заморожен)

**CSS Selector:**
```css
.chat-input-frozen-text
span.chat-input-frozen-text
```

**HTML Structure:**
```html
<span class="chat-input-frozen-text">
    <span class="i18n danger">Your Account is Frozen</span>
    <span class="i18n secondary chat-input-frozen-text-subtitle">
        Click to view details
    </span>
</span>
```

**Классы:**
- `danger` - красный цвет (опасность)
- `secondary` - вторичный текст
- `chat-input-frozen-text-subtitle` - подзаголовок

**Надежность:** ⭐⭐⭐⭐⭐ (очень высокая - критичный индикатор)

**Проверка:**
```python
frozen = page.locator('.chat-input-frozen-text')
if await frozen.count() > 0:
    # Аккаунт заморожен
    pass
```

---

## 7. ДОПОЛНИТЕЛЬНЫЕ ВАЖНЫЕ СЕЛЕКТОРЫ (Additional Important Selectors)

### 7.1. Main Chat Container

**CSS Selector:**
```css
.chat
div.chat.tabs-tab.active
```

**Атрибуты:**
- `data-type="chat"`

**Надежность:** ⭐⭐⭐⭐ (высокая)

---

### 7.2. Chat Background (индикатор загрузки чата)

**CSS Selector:**
```css
.chat-background
div.chat-background
```

**Надежность:** ⭐⭐⭐ (средняя)

---

### 7.3. Закрепленное сообщение (Pinned Message)

**CSS Selector:**
```css
.pinned-message
.pinned-message.pinned-container
```

**Атрибуты:**
- `data-mid` - message ID

**Надежность:** ⭐⭐⭐ (средняя)

---

### 7.4. Scrollable Chat Area

**CSS Selector:**
```css
.scrollable.scrollable-y
```

**Классы:**
- `scrollable` - прокручиваемый
- `scrollable-y` - вертикальная прокрутка
- `tabs-tab` - вкладка
- `chatlist-parts` - части чатлиста
- `folders-scrollable` - прокручиваемые папки

**Надежность:** ⭐⭐⭐ (средняя)

---

## 8. СЕЛЕКТОРЫ ПО НАДЕЖНОСТИ (Selectors Ranked by Reliability)

### ⭐⭐⭐⭐⭐ САМЫЕ НАДЕЖНЫЕ (Most Reliable)

1. **`data-peer-id` attribute** - Уникальный идентификатор чатов/пользователей
   ```css
   [data-peer-id]
   a.chatlist-chat[data-peer-id]
   ```

2. **`.btn-send`** - Кнопка отправки (когда видима)
   ```css
   button.btn-send
   ```

3. **`.input-message-input[contenteditable="true"]`** - Поле ввода сообщения
   ```css
   div.input-message-input[contenteditable="true"]
   ```

4. **`.input-search-input`** - Поле поиска
   ```css
   input.input-search-input
   ```

5. **`.chatlist-chat`** - Элементы чатов (с `data-peer-id`)
   ```css
   a.chatlist-chat[data-peer-id]
   ```

6. **`.chat-input-frozen-text`** - Индикатор замороженного аккаунта
   ```css
   span.chat-input-frozen-text
   ```

7. **`.chat-input-control-button`** - Кнопки ограничений (JOIN, etc.)
   ```css
   button.chat-input-control-button:not(.hide)
   ```

---

### ⭐⭐⭐⭐ НАДЕЖНЫЕ (Reliable)

1. **`.peer-title`** - Названия чатов/пользователей
   ```css
   span.peer-title
   ```

2. **`.input-search-clear`** - Кнопка очистки поиска
   ```css
   button.input-search-clear
   ```

3. **`.chat-info`** - Контейнер информации о чате
   ```css
   div.chat-info
   ```

4. **`.topbar`** - Заголовок открытого чата
   ```css
   .sidebar-header.topbar
   ```

5. **`.dialog-avatar`** - Аватары чатов
   ```css
   .avatar.dialog-avatar
   ```

---

### ⭐⭐⭐ СРЕДНЯЯ НАДЕЖНОСТЬ (Medium Reliability)

1. **`.sending-status`** - Статус отправки (часто меняется)
2. **`.badge.unread`** - Индикаторы непрочитанных
3. **`.message-time`** - Время сообщений

---

### ⚠️ ДИНАМИЧЕСКИЕ КЛАССЫ (Avoid - Dynamic Classes)

**НЕ ИСПОЛЬЗОВАТЬ для автоматизации:**

1. **`_Item_5idej_1`** - Виртуальный список (генерируемые классы)
2. **`is-empty`** - Классы состояния (меняются)
3. **`hide`** - Классы видимости (меняются)
4. **`active`** - Классы состояния (меняются)
5. **Inline styles** - Всегда динамические

---

## 9. ВАЖНЫЕ TIMING CONSIDERATIONS (Timing Considerations)

### 9.1. Search Results
**Проблема:** Результаты появляются не мгновенно после ввода

**Решение:**
```python
# Ввести текст
await search_input.fill('@username')

# Подождать появления результатов
await page.wait_for_selector('.chatlist-chat', timeout=10000)
```

---

### 9.2. Chat Opening
**Проблема:** Чат открывается не сразу после клика

**Решение:**
```python
# Кликнуть на чат
await chat_element.click()

# Подождать topbar и проверить data-peer-id
await page.wait_for_selector('.topbar', timeout=5000)

# Проверить что открыт правильный чат
peer_id = await page.locator('.chat-info .peer-title').get_attribute('data-peer-id')
```

---

### 9.3. Message Input
**Проблема:** Поле ввода может быть недоступно (например, нужно вступить в канал)

**Решение:**
```python
# Проверить доступность поля
input_visible = await page.locator('.input-message-input[contenteditable="true"]').count()

if input_visible == 0:
    # Проверить причину
    join_button = await page.locator('button:has-text("JOIN"):not(.hide)').count()
    if join_button > 0:
        # Нужно вступить
        pass
```

---

### 9.4. Send Button
**Проблема:** Кнопка может быть не видна пока нет текста

**Решение:**
```python
# Ввести текст
await input_field.fill('Message text')

# Подождать появления кнопки
await page.wait_for_selector('button.btn-send:visible', timeout=2000)
```

---

### 9.5. Clear Search
**Проблема:** Кнопка очистки появляется только когда есть текст

**Решение:**
```python
# Проверить наличие текста
if await search_input.input_value():
    # Кнопка должна быть доступна
    await page.locator('.input-search-clear').click()
```

---

## 10. РЕКОМЕНДУЕМЫЕ СТРАТЕГИИ АВТОМАТИЗАЦИИ (Recommended Automation Strategies)

### 10.1. Поиск чата (Search Chat)

```python
async def search_chat(page, username: str) -> bool:
    """
    Поиск чата по username

    Returns:
        True если чат найден, False если нет
    """
    # 1. Найти поле поиска
    search_input = page.locator('input.input-search-input')

    # 2. Очистить поле (если там что-то есть)
    clear_button = page.locator('button.input-search-clear')
    if await clear_button.count() > 0:
        await clear_button.click()
        await page.wait_for_timeout(500)

    # 3. Кликнуть на поле (для фокуса)
    await search_input.click()
    await page.wait_for_timeout(300)

    # 4. Ввести username
    await search_input.fill(username)
    await page.wait_for_timeout(500)

    # 5. Подождать результатов
    try:
        await page.wait_for_selector('.chatlist-chat', timeout=10000)
        return True
    except:
        # Нет результатов
        return False
```

---

### 10.2. Открытие чата (Open Chat)

```python
async def open_chat(page, username: str) -> bool:
    """
    Открыть чат после поиска

    Returns:
        True если чат открылся, False если нет
    """
    # 1. Найти чат по названию (или взять первый результат)
    # Вариант A: По тексту
    chat_element = page.locator(
        f'.chatlist-chat .peer-title:has-text("{username}")'
    ).first

    # Вариант B: Первый результат
    # chat_element = page.locator('.chatlist-chat').first

    # 2. Кликнуть на родительский элемент (весь элемент чата)
    await chat_element.locator('..').click()

    # 3. Подождать открытия чата
    try:
        await page.wait_for_selector('.topbar', timeout=5000)
        return True
    except:
        return False
```

---

### 10.3. Отправка сообщения (Send Message)

```python
async def send_message(page, message_text: str) -> bool:
    """
    Отправить сообщение в открытом чате

    Returns:
        True если отправлено, False если нет
    """
    # 1. Подождать что чат открыт
    await page.wait_for_selector('.topbar', timeout=5000)

    # 2. Проверить доступность отправки
    # Проверить на ограничения
    join_btn = page.locator('button:has-text("JOIN"):not(.hide)')
    if await join_btn.count() > 0:
        raise Exception("Need to join channel")

    frozen = page.locator('.chat-input-frozen-text')
    if await frozen.count() > 0:
        raise Exception("Account is frozen")

    # 3. Найти поле ввода
    input_field = page.locator(
        'div.input-message-input[contenteditable="true"]'
    ).first

    # Проверить что поле доступно
    if await input_field.count() == 0:
        raise Exception("Message input not available")

    # 4. Ввести текст (используем JS для contenteditable)
    await input_field.click()
    await page.wait_for_timeout(300)

    # Вариант A: fill() (может не работать для contenteditable)
    # await input_field.fill(message_text)

    # Вариант B: type() (медленнее, но надежнее)
    await input_field.press_sequentially(message_text, delay=50)

    # Вариант C: JavaScript (самый надежный)
    await page.evaluate(
        f"""
        document.querySelector('.input-message-input[contenteditable="true"]')
            .textContent = '{message_text}'
        """
    )

    # Trigger input event
    await input_field.dispatch_event('input')

    await page.wait_for_timeout(500)

    # 5. Подождать и кликнуть кнопку отправки
    send_button = page.locator('button.btn-send')
    await send_button.wait_for(state='visible', timeout=3000)
    await send_button.click()

    # 6. Подождать подтверждения отправки (опционально)
    await page.wait_for_timeout(1000)

    return True
```

---

### 10.4. Проверка ошибок (Error Checking)

```python
async def check_chat_restrictions(page) -> dict:
    """
    Проверить ограничения в открытом чате

    Returns:
        dict с информацией об ограничениях
    """
    restrictions = {
        'can_send': True,
        'reason': None
    }

    # Проверка 1: Аккаунт заморожен
    frozen = page.locator('.chat-input-frozen-text')
    if await frozen.count() > 0:
        restrictions['can_send'] = False
        restrictions['reason'] = 'account_frozen'
        return restrictions

    # Проверка 2: Нужно вступить в канал
    join_btn = page.locator('button:has-text("JOIN"):not(.hide)')
    if await join_btn.count() > 0:
        restrictions['can_send'] = False
        restrictions['reason'] = 'need_to_join'
        return restrictions

    # Проверка 3: Нужен Premium
    premium = page.locator('button:has-text("Premium"):not(.hide)')
    if await premium.count() > 0:
        restrictions['can_send'] = False
        restrictions['reason'] = 'premium_required'
        return restrictions

    # Проверка 4: Пользователь заблокирован
    unblock_btn = page.locator('button:has-text("Unblock"):not(.hide)')
    if await unblock_btn.count() > 0:
        restrictions['can_send'] = False
        restrictions['reason'] = 'user_blocked'
        return restrictions

    return restrictions
```

---

### 10.5. Полный пример workflow

```python
async def send_to_chat_workflow(page, username: str, message: str):
    """
    Полный цикл: поиск -> открытие -> отправка
    """
    try:
        # 1. Поиск чата
        print(f"Searching for {username}...")
        chat_found = await search_chat(page, username)

        if not chat_found:
            print(f"Chat {username} not found")
            return {
                'status': 'failed',
                'reason': 'chat_not_found'
            }

        # 2. Открытие чата
        print(f"Opening chat {username}...")
        chat_opened = await open_chat(page, username)

        if not chat_opened:
            print(f"Failed to open {username}")
            return {
                'status': 'failed',
                'reason': 'chat_not_opened'
            }

        # 3. Проверка ограничений
        print("Checking restrictions...")
        restrictions = await check_chat_restrictions(page)

        if not restrictions['can_send']:
            print(f"Cannot send: {restrictions['reason']}")
            return {
                'status': 'failed',
                'reason': restrictions['reason']
            }

        # 4. Отправка сообщения
        print(f"Sending message...")
        sent = await send_message(page, message)

        if sent:
            print(f"✓ Message sent to {username}")
            return {
                'status': 'success',
                'chat': username,
                'message': message
            }

    except Exception as e:
        print(f"✗ Error: {e}")
        return {
            'status': 'failed',
            'reason': 'exception',
            'error': str(e)
        }
```

---

## 📌 Важные заметки

### 1. Contenteditable vs Input
Поле ввода сообщения - это **`<div contenteditable="true">`**, а НЕ `<input>` или `<textarea>`.

Это означает:
- `.fill()` может не работать
- Лучше использовать `.type()` или JavaScript
- Нужно trigger'ить `input` event

### 2. Data attributes - самые надежные
Всегда используйте `data-peer-id` для идентификации чатов - это единственный стабильный идентификатор.

### 3. Динамические классы
Избегайте классов вида `_Item_5idej_1` - они генерируются динамически и могут меняться.

### 4. Timing
Всегда добавляйте небольшие задержки (200-500ms) между действиями для имитации человеческого поведения.

### 5. Видимость элементов
Многие элементы имеют класс `.hide` когда не релевантны. Всегда проверяйте `:not(.hide)`.

---

## 🔍 Быстрый справочник

| Действие | Селектор | Надежность |
|----------|----------|------------|
| Поле поиска | `input.input-search-input` | ⭐⭐⭐⭐⭐ |
| Очистить поиск | `button.input-search-clear` | ⭐⭐⭐⭐⭐ |
| Элемент чата | `a.chatlist-chat[data-peer-id]` | ⭐⭐⭐⭐⭐ |
| Название чата | `span.peer-title` | ⭐⭐⭐⭐⭐ |
| Topbar (чат открыт) | `.topbar` | ⭐⭐⭐⭐⭐ |
| Поле ввода | `.input-message-input[contenteditable="true"]` | ⭐⭐⭐⭐⭐ |
| Кнопка отправки | `button.btn-send` | ⭐⭐⭐⭐⭐ |
| Аккаунт заморожен | `.chat-input-frozen-text` | ⭐⭐⭐⭐⭐ |
| Нужно вступить | `button:has-text("JOIN"):not(.hide)` | ⭐⭐⭐⭐⭐ |

---

**Статус:** ✅ Завершено
**Версия документа:** 1.0
**Последнее обновление:** 2024-11-15
**Основано на:** HTML файлы из /tg-automatizamtion/htmls/
