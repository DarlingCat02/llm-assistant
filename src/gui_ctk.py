"""
GUI на CustomTkinter для Local AI Assistant.

Модуль предоставляет графический интерфейс на базе customtkinter —
стабильной кроссплатформенной библиотеки с современным видом.

Архитектурные решения:
1. GUI принимает экземпляр Assistant и использует его методы
2. Долгие операции (LLM, память) выполняются в отдельном потоке
3. Обновление GUI происходит в главном потоке через after()

Требования:
- customtkinter>=5.2.0

Пример использования:
    from src.main import Assistant
    from src.gui_ctk import AssistantGUI
    
    async def main():
        assistant = Assistant()
        await assistant.initialize()
        gui = AssistantGUI(assistant)
        gui.build()
"""

import asyncio
import logging
import threading
import queue
from datetime import datetime
from typing import Optional, Callable

import customtkinter as ctk

from config import Config
from src.main import Assistant


logger = logging.getLogger(__name__)


class ChatMessageFrame(ctk.CTkFrame):
    """
    Фрейм сообщения в чате.
    
    Отображает сообщение в виде "пузыря" с указанием
    отправителя (пользователь или ассистент).
    """
    
    def __init__(
        self,
        master,
        text: str,
        is_user: bool = False,
        timestamp: Optional[datetime] = None,
        **kwargs
    ):
        super().__init__(master, **kwargs)
        self.text = text
        self.is_user = is_user
        self.timestamp = timestamp or datetime.now()
        
        # Цвета
        self.user_color = "#1E90FF"  # DodgerBlue
        self.assistant_color = "#2E8B57"  # SeaGreen
        
        self._build()
    
    def _build(self) -> None:
        """Построить фрейм сообщения."""
        # Настраиваем цвета и выравнивание
        bg_color = self.user_color if self.is_user else self.assistant_color
        anchor = "e" if self.is_user else "w"
        
        # Контейнер для выравнивания
        align_frame = ctk.CTkFrame(self, fg_color="transparent")
        align_frame.pack(fill="both", expand=True, padx=5, pady=2)
        
        # Пузырь сообщения
        bubble = ctk.CTkLabel(
            align_frame,
            text=self.text,
            fg_color=bg_color,
            text_color="white",
            corner_radius=15,
            padx=12,
            pady=8,
            wraplength=500,
            justify="left",
        )
        
        # Выравнивание
        if self.is_user:
            bubble.pack(side="right", anchor="e")
        else:
            bubble.pack(side="left", anchor="w")
        
        # Время
        time_str = self.timestamp.strftime("%H:%M")
        time_label = ctk.CTkLabel(
            self,
            text=time_str,
            text_color="gray",
            font=ctk.CTkFont(size=10),
        )
        
        if self.is_user:
            time_label.pack(anchor="e", padx=5)
        else:
            time_label.pack(anchor="w", padx=5)


class AssistantGUI:
    """
    Графический интерфейс для AI ассистента на CustomTkinter.
    
    Использует threading для асинхронных операций,
    чтобы GUI не зависал во время генерации ответов.
    
    Структура интерфейса:
    ┌─────────────────────────────────────────┐
    │  Local AI Assistant               [_][X]│
    ├─────────────────────────────────────────┤
    │  ┌───────────────────────────────────┐  │
    │  │ 🤖 Привет! Чем могу помочь?       │  │
    │  │                            10:30  │  │
    │  │ ┌─────────────────────────────┐   │  │
    │  │ │    Привет! Расскажи о себе  │   │  │
    │  │ │                      10:31  │   │  │
    │  └─┴─────────────────────────────┴───┘  │
    │                                         │
    │  Статус: Печатает...                    │
    ├─────────────────────────────────────────┤
    │  [Поле ввода...]          [Отправить]   │
    ├─────────────────────────────────────────┤
    │  [Очистить] [Статистика]          [Выход]│
    └─────────────────────────────────────────┘
    """
    
    def __init__(self, assistant: Assistant):
        """
        Инициализировать GUI.
        
        Args:
            assistant: Инициализированный экземпляр Assistant.
        """
        self.assistant = assistant
        self.config = assistant._config
        
        # Основное окно
        self.root: Optional[ctk.CTk] = None
        
        # Элементы интерфейса
        self._chat_frame: Optional[ctk.CTkScrollableFrame] = None
        self._message_input: Optional[ctk.CTkEntry] = None
        self._status_label: Optional[ctk.CTkLabel] = None
        
        # Очередь для сообщений из потока
        self._message_queue: queue.Queue = queue.Queue()
        
        # Флаг работы
        self._running = False
        
        logger.info("AssistantGUI (CustomTkinter) инициализирован")
    
    def build(self) -> None:
        """
        Построить и показать интерфейс.
        
        Запускает главный цикл tkinter.
        """
        # Создаём главное окно
        self.root = ctk.CTk()
        self.root.title(self.config.gui.title)
        self.root.geometry(f"{self.config.gui.width}x{self.config.gui.height}")
        
        # Настраиваем тему
        ctk.set_appearance_mode(self.config.gui.theme)
        ctk.set_default_color_theme("blue")
        
        # Центрирование окна
        self._center_window()
        
        # Создаём элементы
        self._create_chat_area()
        self._create_status_bar()
        self._create_input_area()
        self._create_button_bar()
        
        # Обработчик закрытия
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Добавляем приветственное сообщение
        self._add_message("🤖 Привет! Я ваш локальный AI-ассистент.\n\n"
                         f"Провайдер: {self.config.llm.provider.value}\n"
                         f"Модель: {self.config.llm.model}\n"
                         f"Память: ChromaDB\n\n"
                         f"Чем могу помочь?", is_user=False)
        
        self._update_status("Готов к работе")
        
        # Запускаем обработку очереди сообщений
        self._running = True
        self._process_queue()
        
        logger.debug("GUI построен")
        
        # Запускаем главный цикл
        self.root.mainloop()
    
    def _center_window(self) -> None:
        """Центрировать окно на экране."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _create_chat_area(self) -> None:
        """Создать область чата с историей сообщений."""
        # Контейнер
        chat_container = ctk.CTkFrame(self.root, fg_color="transparent")
        chat_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Заголовок
        title_label = ctk.CTkLabel(
            chat_container,
            text="💬 История диалога",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        title_label.pack(anchor="w", pady=(0, 5))
        
        # Прокручиваемая область для сообщений
        self._chat_frame = ctk.CTkScrollableFrame(
            chat_container,
        )
        self._chat_frame.pack(fill="both", expand=True)
    
    def _create_status_bar(self) -> None:
        """Создать строку статуса."""
        status_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        status_frame.pack(fill="x", padx=10, pady=5)
        
        self._status_label = ctk.CTkLabel(
            status_frame,
            text="Статус: Ожидание",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self._status_label.pack(anchor="w")
    
    def _create_input_area(self) -> None:
        """Создать область ввода сообщения."""
        input_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        input_frame.pack(fill="x", padx=10, pady=10)
        
        # Поле ввода
        self._message_input = ctk.CTkEntry(
            input_frame,
            placeholder_text="Введите сообщение...",
            height=40,
            font=ctk.CTkFont(size=14),
        )
        self._message_input.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._message_input.bind("<Return>", lambda e: self._on_send())
        
        # Кнопка отправки
        send_button = ctk.CTkButton(
            input_frame,
            text="➤ Отправить",
            width=120,
            height=40,
            font=ctk.CTkFont(size=14),
            command=self._on_send,
        )
        send_button.pack(side="right")
    
    def _create_button_bar(self) -> None:
        """Создать панель кнопок команд."""
        button_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        # Кнопка очистки
        clear_button = ctk.CTkButton(
            button_frame,
            text="🧹 Очистить",
            width=120,
            command=self._on_clear,
        )
        clear_button.pack(side="left", padx=5)
        
        # Кнопка статистики
        stats_button = ctk.CTkButton(
            button_frame,
            text="📊 Статистика",
            width=120,
            command=self._on_stats,
        )
        stats_button.pack(side="left", padx=5)
        
        # Распорка
        spacer = ctk.CTkFrame(button_frame, fg_color="transparent", width=1)
        spacer.pack(side="left", fill="x", expand=True)
        
        # Кнопка выхода
        exit_button = ctk.CTkButton(
            button_frame,
            text="❌ Выход",
            width=120,
            fg_color="#DC143C",  # Crimson
            hover_color="#B22222",  # Firebrick
            command=self._on_exit,
        )
        exit_button.pack(side="right", padx=5)
    
    def _add_message(self, text: str, is_user: bool = False) -> None:
        """
        Добавить сообщение в чат.
        
        Args:
            text: Текст сообщения.
            is_user: True если сообщение от пользователя.
        """
        # Создаём фрейм сообщения
        message_frame = ChatMessageFrame(
            self._chat_frame,
            text=text,
            is_user=is_user,
        )
        message_frame.pack(fill="x", pady=5)
        
        # Автопрокрутка вниз
        self._chat_frame._scrollbar.set(1.0, 1.0)
        self._chat_frame.update_idletasks()
    
    def _update_status(self, status: str) -> None:
        """
        Обновить текст статуса.
        
        Args:
            status: Новый текст статуса.
        """
        if self._status_label:
            self._status_label.configure(text=f"Статус: {status}")
    
    def _on_send(self) -> None:
        """
        Обработать отправку сообщения.
        
        1. Получает текст из поля ввода
        2. Добавляет сообщение пользователя в чат
        3. Запускает обработку в отдельном потоке
        4. Очищает поле ввода
        """
        if not self._message_input:
            return
        
        user_text = self._message_input.get().strip()
        if not user_text:
            return
        
        # Очищаем поле ввода
        self._message_input.delete(0, "end")
        
        # Добавляем сообщение пользователя
        self._add_message(user_text, is_user=True)
        self._update_status("Обработка...")
        
        # Запускаем обработку в отдельном потоке
        thread = threading.Thread(
            target=self._process_message_thread,
            args=(user_text,),
            daemon=True,
        )
        thread.start()
    
    def _process_message_thread(self, user_text: str) -> None:
        """
        Поток обработки сообщения.
        
        Args:
            user_text: Сообщение пользователя.
        """
        try:
            # Используем синхронную версию для работы в потоке
            answer = self.assistant.process_message_sync(user_text)
            
            # Ставим ответ в очередь для обновления GUI
            self._message_queue.put(("answer", answer))
                
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {e}", exc_info=True)
            self._message_queue.put(("error", str(e)))
    
    def _process_queue(self) -> None:
        """
        Обработать очередь сообщений.
        
        Вызывается периодически из главного потока для
        обновления GUI результатами из потока обработки.
        """
        try:
            while True:
                msg_type, data = self._message_queue.get_nowait()
                
                if msg_type == "answer":
                    self._add_message(data, is_user=False)
                    self._update_status("Готов к работе")
                elif msg_type == "error":
                    self._add_message(f"❌ Ошибка: {data}", is_user=False)
                    self._update_status("Ошибка")
                    
        except queue.Empty:
            pass
        
        # Планируем следующую проверку через 100мс
        if self._running and self.root:
            self.root.after(100, self._process_queue)
    
    def _on_clear(self) -> None:
        """Очистить историю диалога."""
        # Очищаем историю в ассистенте
        self.assistant._llm.clear_history()
        
        # Очищаем GUI
        for widget in self._chat_frame.winfo_children():
            widget.destroy()
        
        # Добавляем приветственное сообщение
        self._add_message(
            "🤖 Привет! Я ваш локальный AI-ассистент.\n\n"
            f"Провайдер: {self.config.llm.provider.value}\n"
            f"Модель: {self.config.llm.model}\n"
            f"Память: ChromaDB\n\n"
            f"Чем могу помочь?",
            is_user=False
        )
        self._update_status("Готов к работе")
        
        logger.info("История диалога очищена")
    
    def _on_stats(self) -> None:
        """Показать статистику."""
        # Получаем статистику
        stats = {
            "Сообщений в сессии": self.assistant._message_count,
        }
        
        if self.assistant._start_time:
            duration = datetime.now() - self.assistant._start_time
            stats["Время работы"] = str(duration).split('.')[0]
        
        # Получаем статистику памяти в отдельном потоке
        def get_memory_stats_sync():
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self.assistant._memory.get_stats())
            finally:
                loop.close()
        
        try:
            import threading
            result = [None]
            def run_in_thread():
                result[0] = get_memory_stats_sync()
            t = threading.Thread(target=run_in_thread)
            t.start()
            t.join(timeout=5)
            if result[0] is not None:
                stats["Записей в памяти"] = result[0].get("total_entries", "N/A")
            else:
                stats["Записей в памяти"] = "N/A"
        except Exception:
            stats["Записей в памяти"] = "N/A"
        
        # Форматируем в текст
        stats_text = "📊 Статистика:\n\n"
        for key, value in stats.items():
            stats_text += f"• {key}: {value}\n"
        
        # Показываем в диалоге
        self._show_dialog("📊 Статистика", stats_text)
    
    def _show_dialog(self, title: str, message: str) -> None:
        """
        Показать диалоговое окно.
        
        Args:
            title: Заголовок диалога.
            message: Текст сообщения.
        """
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(title)
        dialog.geometry("400x300")
        dialog.resizable(False, False)
        
        # Центрирование
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Текст сообщения
        text_widget = ctk.CTkTextbox(
            dialog,
            wrap="word",
            font=ctk.CTkFont(size=13),
        )
        text_widget.pack(fill="both", expand=True, padx=20, pady=20)
        text_widget.insert("1.0", message)
        text_widget.configure(state="disabled")
        
        # Кнопка закрытия
        close_button = ctk.CTkButton(
            dialog,
            text="Закрыть",
            command=dialog.destroy,
            width=100,
        )
        close_button.pack(pady=(0, 20))
    
    def _on_exit(self) -> None:
        """Выйти из приложения."""
        logger.info("Выход из приложения через GUI")
        self._running = False
        self.root.destroy()
    
    def _on_close(self) -> None:
        """Обработчик закрытия окна."""
        self._on_exit()


def run_gui(assistant: Assistant) -> None:
    """
    Запустить GUI в отдельном потоке.
    
    Args:
        assistant: Инициализированный экземпляр Assistant.
    """
    gui = AssistantGUI(assistant)
    gui.build()
