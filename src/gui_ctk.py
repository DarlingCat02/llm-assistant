"""
CustomTkinter GUI for the Local AI Assistant.

The module provides a graphical interface based on customtkinter —
a stable cross-platform library with a modern look.

Architectural decisions:
1. The GUI takes an Assistant instance and uses its methods
2. Long operations (LLM, memory) run in a separate thread
3. GUI updates happen in the main thread via after()

Requirements:
- customtkinter>=5.2.0

Example usage:
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
    Chat message frame.

    Displays a message as a "bubble" indicating
    the sender (user or assistant).
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
        
        # Colors
        self.user_color = "#1E90FF"  # DodgerBlue
        self.assistant_color = "#2E8B57"  # SeaGreen
        
        self._build()
    
    def _build(self) -> None:
        """Build the message frame."""
        # Set up colors and alignment
        bg_color = self.user_color if self.is_user else self.assistant_color
        anchor = "e" if self.is_user else "w"
        
        # Container for alignment
        align_frame = ctk.CTkFrame(self, fg_color="transparent")
        align_frame.pack(fill="both", expand=True, padx=5, pady=2)
        
        # Message bubble
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
        
        # Alignment
        if self.is_user:
            bubble.pack(side="right", anchor="e")
        else:
            bubble.pack(side="left", anchor="w")
        
        # Time
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
    Graphical interface for the AI assistant on CustomTkinter.

    Uses threading for async operations
    so the GUI does not freeze while generating responses.

    Interface structure:
    ┌─────────────────────────────────────────┐
    │  Local AI Assistant               [_][X]│
    ├─────────────────────────────────────────┤
    │  ┌───────────────────────────────────┐  │
    │  │ 🤖 Hello! How can I help?         │  │
    │  │                            10:30  │  │
    │  │ ┌─────────────────────────────┐   │  │
    │  │ │    Hello! Tell me about     │   │  │
    │  │ │    yourself                 │   │  │
    │  │ │                      10:31  │   │  │
    │  └─┴─────────────────────────────┴───┘  │
    │                                         │
    │  Status: Typing...                      │
    ├─────────────────────────────────────────┤
    │  [Input field...]          [Send]       │
    ├─────────────────────────────────────────┤
    │  [Clear] [Stats]              [Exit]    │
    └─────────────────────────────────────────┘
    """
    
    def __init__(self, assistant: Assistant):
        """
        Initialize the GUI.

        Args:
            assistant: Initialized Assistant instance.
        """
        self.assistant = assistant
        self.config = assistant._config
        
        # Main window
        self.root: Optional[ctk.CTk] = None
        
        # Interface elements
        self._chat_frame: Optional[ctk.CTkScrollableFrame] = None
        self._message_input: Optional[ctk.CTkEntry] = None
        self._status_label: Optional[ctk.CTkLabel] = None
        
        # Queue for messages from the thread
        self._message_queue: queue.Queue = queue.Queue()
        
        # Running flag
        self._running = False
        
        logger.info("AssistantGUI (CustomTkinter) initialized")
    
    def build(self) -> None:
        """
        Build and show the interface.

        Runs the main tkinter loop.
        """
        # Create the main window
        self.root = ctk.CTk()
        self.root.title(self.config.gui.title)
        self.root.geometry(f"{self.config.gui.width}x{self.config.gui.height}")
        
        # Set up the theme
        ctk.set_appearance_mode(self.config.gui.theme)
        ctk.set_default_color_theme("blue")
        
        # Center the window
        self._center_window()
        
        # Create elements
        self._create_chat_area()
        self._create_status_bar()
        self._create_input_area()
        self._create_button_bar()
        
        # Close handler
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Add a welcome message
        self._add_message("🤖 Привет! Я ваш локальный AI-ассистент.\n\n"
                         f"Провайдер: {self.config.llm.provider.value}\n"
                         f"Модель: {self.config.llm.model}\n"
                         f"Память: ChromaDB\n\n"
                         f"Чем могу помочь?", is_user=False)

        self._update_status("Готов к работе")

        # Start queue processing
        self._running = True
        self._process_queue()
        
        logger.debug("GUI built")
        
        # Start the main loop
        self.root.mainloop()
    
    def _center_window(self) -> None:
        """Center the window on the screen."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _create_chat_area(self) -> None:
        """Create the chat area with message history."""
        # Container
        chat_container = ctk.CTkFrame(self.root, fg_color="transparent")
        chat_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Title
        title_label = ctk.CTkLabel(
            chat_container,
            text="💬 История диалога",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        title_label.pack(anchor="w", pady=(0, 5))
        
        # Scrollable area for messages
        self._chat_frame = ctk.CTkScrollableFrame(
            chat_container,
        )
        self._chat_frame.pack(fill="both", expand=True)
    
    def _create_status_bar(self) -> None:
        """Create the status bar."""
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
        """Create the message input area."""
        input_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        input_frame.pack(fill="x", padx=10, pady=10)
        
        # Input field
        self._message_input = ctk.CTkEntry(
            input_frame,
            placeholder_text="Введите сообщение...",
            height=40,
            font=ctk.CTkFont(size=14),
        )
        self._message_input.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._message_input.bind("<Return>", lambda e: self._on_send())
        
        # Send button
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
        """Create the command button bar."""
        button_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        # Clear button
        clear_button = ctk.CTkButton(
            button_frame,
            text="🧹 Очистить",
            width=120,
            command=self._on_clear,
        )
        clear_button.pack(side="left", padx=5)
        
        # Stats button
        stats_button = ctk.CTkButton(
            button_frame,
            text="📊 Статистика",
            width=120,
            command=self._on_stats,
        )
        stats_button.pack(side="left", padx=5)
        
        # Spacer
        spacer = ctk.CTkFrame(button_frame, fg_color="transparent", width=1)
        spacer.pack(side="left", fill="x", expand=True)
        
        # Exit button
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
        Add a message to the chat.

        Args:
            text: Message text.
            is_user: True if the message is from the user.
        """
        # Create the message frame
        message_frame = ChatMessageFrame(
            self._chat_frame,
            text=text,
            is_user=is_user,
        )
        message_frame.pack(fill="x", pady=5)
        
        # Auto-scroll down
        self._chat_frame._scrollbar.set(1.0, 1.0)
        self._chat_frame.update_idletasks()
    
    def _update_status(self, status: str) -> None:
        """
        Update the status text.

        Args:
            status: New status text.
        """
        if self._status_label:
            self._status_label.configure(text=f"Статус: {status}")
    
    def _on_send(self) -> None:
        """
        Handle message sending.

        1. Gets text from the input field
        2. Adds the user message to the chat
        3. Starts processing in a separate thread
        4. Clears the input field
        """
        if not self._message_input:
            return
        
        user_text = self._message_input.get().strip()
        if not user_text:
            return
        
        # Clear the input field
        self._message_input.delete(0, "end")
        
        # Add the user message
        self._add_message(user_text, is_user=True)
        self._update_status("Обработка...")
        
        # Start processing in a separate thread
        thread = threading.Thread(
            target=self._process_message_thread,
            args=(user_text,),
            daemon=True,
        )
        thread.start()
    
    def _process_message_thread(self, user_text: str) -> None:
        """
        Message processing thread.

        Args:
            user_text: User message.
        """
        try:
            # Use the sync version for working in a thread
            answer = self.assistant.process_message_sync(user_text)
            
            # Put the answer into the queue for GUI update
            self._message_queue.put(("answer", answer))
                
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            self._message_queue.put(("error", str(e)))
    
    def _process_queue(self) -> None:
        """
        Process the message queue.

        Called periodically from the main thread to
        update the GUI with results from the processing thread.
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
        
        # Schedule the next check in 100ms
        if self._running and self.root:
            self.root.after(100, self._process_queue)
    
    def _on_clear(self) -> None:
        """Clear the dialog history."""
        # Clear history in the assistant
        self.assistant._llm.clear_history()
        
        # Clear the GUI
        for widget in self._chat_frame.winfo_children():
            widget.destroy()
        
        # Add a welcome message
        self._add_message(
            "🤖 Привет! Я ваш локальный AI-ассистент.\n\n"
            f"Провайдер: {self.config.llm.provider.value}\n"
            f"Модель: {self.config.llm.model}\n"
            f"Память: ChromaDB\n\n"
            f"Чем могу помочь?",
            is_user=False
        )
        self._update_status("Готов к работе")
        
        logger.info("Dialog history cleared")
    
    def _on_stats(self) -> None:
        """Show statistics."""
        # Get statistics
        stats = {
            "Сообщений в сессии": self.assistant._message_count,
        }
        
        if self.assistant._start_time:
            duration = datetime.now() - self.assistant._start_time
            stats["Время работы"] = str(duration).split('.')[0]
        
        # Get memory stats in a separate thread
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
        
        # Format as text
        stats_text = "📊 Статистика:\n\n"
        for key, value in stats.items():
            stats_text += f"• {key}: {value}\n"
        
        # Show in a dialog
        self._show_dialog("📊 Статистика", stats_text)
    
    def _show_dialog(self, title: str, message: str) -> None:
        """
        Show a dialog window.

        Args:
            title: Dialog title.
            message: Message text.
        """
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(title)
        dialog.geometry("400x300")
        dialog.resizable(False, False)
        
        # Centering
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Message text
        text_widget = ctk.CTkTextbox(
            dialog,
            wrap="word",
            font=ctk.CTkFont(size=13),
        )
        text_widget.pack(fill="both", expand=True, padx=20, pady=20)
        text_widget.insert("1.0", message)
        text_widget.configure(state="disabled")
        
        # Close button
        close_button = ctk.CTkButton(
            dialog,
            text="Закрыть",
            command=dialog.destroy,
            width=100,
        )
        close_button.pack(pady=(0, 20))
    
    def _on_exit(self) -> None:
        """Exit the application."""
        logger.info("Exit via GUI")
        self._running = False
        self.root.destroy()
    
    def _on_close(self) -> None:
        """Window close handler."""
        self._on_exit()


def run_gui(assistant: Assistant) -> None:
    """
    Run the GUI in a separate thread.

    Args:
        assistant: Initialized Assistant instance.
    """
    gui = AssistantGUI(assistant)
    gui.build()
