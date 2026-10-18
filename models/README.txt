MODELS - what this folder must contain
=====================================

Three models live here. The folder NAMES are fixed: the app looks them up by
name and checks only that a folder with that name exists, never what is inside
it. A folder that is empty or holds something else fails later, with a much
worse message than the one you get now.

  models/omnivoice            speech synthesis (voice output)
  models/whisper-<alias>      speech recognition (voice input)
  models/all-MiniLM-L6-v2     memory embeddings (long-term memory)

The third one is downloaded automatically on first start if it is missing, and
is then used fully offline. The other two are not: without them their features
simply do not work.


The Whisper folder name depends on STT_MODEL in .env
------------------------------------------------------

  STT_MODEL=tiny              ->  models/whisper-tiny
  STT_MODEL=base              ->  models/whisper-base
  STT_MODEL=small             ->  models/whisper-small
  STT_MODEL=medium            ->  models/whisper-medium
  STT_MODEL=large             ->  models/whisper-large-v3      (v3, not "large")
  STT_MODEL=large-v3-turbo    ->  models/whisper-large-v3-turbo   (default)

The wake word needs no model of its own: it borrows this same Whisper.


What a working folder contains
-------------------------------

Speech recognition, in the transformers format that the app loads:

  config.json, model.safetensors, tokenizer.json, tokenizer_config.json,
  preprocessor_config.json, generation_config.json, merges.txt,
  normalizer.json, special_tokens_map.json, added_tokens.json

Speech synthesis (omnivoice):

  config.json, model.safetensors, tokenizer.json, tokenizer_config.json

Memory embeddings:

  config.json, model.safetensors, tokenizer.json, vocab.txt, modules.json,
  config_sentence_transformers.json, sentence_bert_config.json,
  special_tokens_map.json, tokenizer_config.json


Do not copy these by hand
------------------------

It is easy to get a folder that looks right and is not - a raw .bin from a
mirror, a git clone without the weights, or a snapshot cut short. Let the app
fetch them:

  install.bat                                  options 3 and 4, or 8 for all
  venv\Scripts\python tests\fetch_whisper_model.py large-v3-turbo
  venv\Scripts\python tests\fetch_whisper_model.py --embedding

If the name does not match STT_MODEL, the app does not complain about the
folder: it goes off to download the model instead, and on a machine without
internet that ends as a download error rather than "your folder is named wrong".

Any folder name works for speech recognition if you point STT_MODEL straight at
it - an absolute path is used as it is:

  STT_MODEL=D:\models\my-whisper


---
ЗАПИСКА ПО-РУССКИ

В этой папке живут три модели. Имена папок фиксированы: приложение ищет их по
имени и проверяет только, что папка с таким именем есть - что внутри, не
проверяет. Пустая или неправильная папка сломается позже и с заметно худшим
сообщением.

  models/omnivoice            озвучка
  models/whisper-<алиас>      распознавание речи
  models/all-MiniLM-L6-v2     эмбеддинги для памяти (скачиваются сами при
                              первом запуске, если их нет)

Имя папки Whisper зависит от STT_MODEL в .env: tiny -> whisper-tiny,
base -> whisper-base, small -> whisper-small, medium -> whisper-medium,
large -> whisper-large-v3 (именно v3), large-v3-turbo -> whisper-large-v3-turbo
(по умолчанию). Фразе пробуждения отдельная модель не нужна - она берёт эту же.

Что должно лежать в рабочей папке распознавания: config.json, model.safetensors,
tokenizer.json, tokenizer_config.json, preprocessor_config.json,
generation_config.json, merges.txt, normalizer.json, special_tokens_map.json,
added_tokens.json. В omnivoice: config.json, model.safetensors, tokenizer.json,
tokenizer_config.json.

Лучше не копировать руками: install.bat (пункты 3 и 4, либо 8) или
venv\Scripts\python tests\fetch_whisper_model.py large-v3-turbo

Если имя папки не совпадает с STT_MODEL, приложение не пожалуется на папку, а
попробует скачать модель - и без интернета закончит ошибкой загрузки. Любое
имя папки подходит, если указать путь прямо в STT_MODEL, например
STT_MODEL=D:\models\my-whisper