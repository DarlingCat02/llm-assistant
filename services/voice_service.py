"""
Голосовой сервис (будущая реализация).

Этот модуль будет:
1. Слушать глобальные горячие клавиши (pynput)
2. Записывать аудио через микрофон (speech_recognition)
3. Отправлять аудио на FastAPI бэкенд (/api/voice)
4. Получать транскрибацию и отправлять в чат

Архитектурные решения:
- Отдельный процесс от веб-сервера
- Работает в фоне даже при закрытом браузере
- Использует тот же бэкенд API что и веб-интерфейс

TODO для будущей реализации:
1. pip install pynput speechrecognition pyaudio
2. Реализовать захват горячей клавиши
3. Реализовать запись аудио
4. Отправка на /api/voice
"""

import logging
import threading
import time
from typing import Optional

# TODO: Раскомментировать при реализации
# from pynput import keyboard
# import speech_recognition as sr
# import requests


logger = logging.getLogger(__name__)


class VoiceService:
    """
    Сервис голосового ввода.
    
    Будущая реализация:
    - Слушает горячую клавишу (по умолчанию F12)
    - Записывает аудио с микрофона
    - Отправляет на бэкенд для транскрибации
    - Получает текст и отправляет в чат
    """
    
    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        hotkey: str = "F12",
    ):
        """
        Инициализировать голосовой сервис.
        
        Args:
            api_url: URL бэкенда API.
            hotkey: Горячая клавиша для активации.
        """
        self._api_url = api_url
        self._hotkey = hotkey
        self._running = False
        self._recording = False
        self._listener_thread: Optional[threading.Thread] = None
        
        # TODO: При реализации раскомментировать
        # self._recognizer = sr.Recognizer()
        # self._hotkey_pressed = False
    
    def start(self) -> None:
        """
        Запустить сервис в отдельном потоке.
        """
        if self._running:
            logger.warning("Голосовой сервис уже запущен")
            return
        
        self._running = True
        self._listener_thread = threading.Thread(
            target=self._listener_loop,
            daemon=True,
        )
        self._listener_thread.start()
        
        logger.info(f"Голосовой сервис запущен (горячая клавиша: {self._hotkey})")
    
    def stop(self) -> None:
        """
        Остановить сервис.
        """
        self._running = False
        
        if self._listener_thread:
            self._listener_thread.join(timeout=5)
        
        logger.info("Голосовой сервис остановлен")
    
    def _listener_loop(self) -> None:
        """
        Основной цикл прослушивания горячей клавиши.
        
        TODO: Реализовать с pynput
        """
        logger.info("Ожидание нажатия горячей клавиши...")
        
        while self._running:
            # TODO: Реализовать прослушивание горячей клавиши
            # Пример с pynput:
            # with keyboard.Listener(on_press=self._on_press) as listener:
            #     listener.join()
            
            time.sleep(0.1)
    
    def _on_press(self, key) -> None:
        """
        Обработчик нажатия клавиши.
        
        Args:
            key: Нажатая клавиша.
        
        TODO: Реализовать с pynput
        """
        # TODO: Проверить нажатие горячей клавиши
        # if key == keyboard.KeyCode.from_char(self._hotkey.lower()):
        #     self._start_recording()
        pass
    
    def _start_recording(self) -> None:
        """
        Начать запись аудио.
        
        TODO: Реализовать с speech_recognition
        """
        if self._recording:
            return
        
        self._recording = True
        logger.info("Запись аудио...")
        
        # TODO: Реализовать запись
        # with sr.Microphone() as source:
        #     audio = self._recognizer.listen(source)
        #     self._process_audio(audio)
        
        self._recording = False
    
    def _process_audio(self, audio_data) -> None:
        """
        Обработать аудио данные.
        
        Args:
            audio_data: Аудио данные для транскрибации.
        
        TODO: Реализовать транскрибацию и отправку на бэкенд
        """
        logger.info("Обработка аудио...")
        
        # TODO: Транскрибация локально
        # try:
        #     text = self._recognizer.recognize_whisper(audio_data)
        #     logger.info(f"Распознано: {text}")
        #     
        #     # Отправка на бэкенд
        #     self._send_to_backend(text)
        #     
        # except sr.UnknownValueError:
        #     logger.warning("Аудио не распознано")
        # except sr.RequestError as e:
        #     logger.error(f"Ошибка распознавания: {e}")
        pass
    
    def _send_to_backend(self, text: str) -> None:
        """
        Отправить текст на бэкенд.
        
        Args:
            text: Распознанный текст.
        """
        try:
            # TODO: Отправка на /api/chat
            # response = requests.post(
            #     f"{self._api_url}/api/chat",
            #     json={"message": text},
            # )
            # response.raise_for_status()
            logger.info(f"Текст отправлен на бэкенд: {text[:50]}...")
        except Exception as e:
            logger.error(f"Ошибка отправки на бэкенд: {e}")


def main():
    """
    Точка входа для голосового сервиса.
    
    Запускается как отдельный процесс.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    logger.info("Запуск голосового сервиса (заглушка)...")
    logger.info("Для активации реализуйте код в voice_service.py")
    
    service = VoiceService()
    
    try:
        service.start()
        
        # Держим сервис запущенным
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Остановка по Ctrl+C")
    finally:
        service.stop()


if __name__ == "__main__":
    main()
