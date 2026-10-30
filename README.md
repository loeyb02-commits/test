# PenASMR — Windows 11 / Wacom 필기 마찰음 실험 프로그램

OneNote를 그대로 사용하면서 Wintab이 제공하는 펜 좌표·필압을 관찰하고,
이동 속도에 따라 공간 텍스처를 진행시켜 연필 마찰음을 합성합니다.
**Windows/Wacom 실기 검증 전의 프로토타입입니다. OneNote 동시 수집 성공을 보장하지 않습니다.**

## 실행

1. Windows 11에 공식 Wacom 드라이버와 Python **3.13 x64**(Tk 포함)를 설치합니다.
2. Windows Ink를 켠 상태로 유지합니다. OneNote 설정을 바꿀 필요는 없습니다.
3. 이 폴더의 `run.cmd`를 실행합니다. 최초에는 인터넷과 패키지 설치가 필요합니다.
4. 프로그램을 켠 채 OneNote로 전환해서 필기합니다. 최소화해도 폴링과 출력은 계속됩니다.
5. 볼륨은 낮게 시작하세요. ON/OFF, 볼륨, 필압 곡선, 속도 텍스처 반응을 조절할 수 있습니다.
   설정은 종료 시 `%LOCALAPPDATA%\PenASMR\settings.json`에 저장됩니다.

사용자가 제시한 Python 3.15.2에서는 이 환경에서 실행 및 wheel/패키징 호환성을
검증하지 못했습니다. 기존 Python을 지울 필요 없이 3.13을 나란히 설치할 수 있습니다.
이미 호환되는 환경이 있다면 `python -m pip install -r requirements.txt`, `python run.py`로 실행합니다.

## EXE 만들기

Windows에서 `build.cmd` 실행 후 `dist\PenASMR\PenASMR.exe`를 실행합니다.
**배포 시 PenASMR 폴더 전체**를 복사하세요. 대상 PC에 Python 설치는 필요 없습니다.
현재 Linux 클라우드에서는 Windows EXE를 빌드하거나 검증하지 않았습니다.
빌드 스크립트가 제공되며 완성된 EXE는 포함되어 있지 않습니다.

## 입력 방식 검토 및 구현

* Wintab: `WTI_DEFSYSCTX` 기반 시스템/펜 컨텍스트, 절대 좌표와 압력 패킷,
  정확한 ctypes 함수 포인터/64비트 HANDLE 선언, `WTPacketsGet`으로 4ms 간격 폴링.
  `WTOverlap(TRUE)`를 호출하지 않아 OneNote 위로 컨텍스트를 승격하지 않습니다.
  메시지 수신 구현에 의존하지 않으므로 잘못된 WM_PACKET 처리 문제를 피합니다.
  다만 드라이버의 컨텍스트 라우팅/우선순위 정책 때문에 타 앱 활성화 시 패킷이 멈출 수 있습니다.
* Windows Ink: 일반 HWND의 WM_POINTERUPDATE는 전역 구독 API가 아닙니다.
  이벤트 몇 개 또는 압력 0만으로 펜/백그라운드 지원을 입증할 수 없습니다.
  OneNote 이벤트를 가로채거나 Windows Ink를 끄는 방식은 구현하지 않았습니다.
* Raw Input: RIDEV_INPUTSINK로 백그라운드 HID 관찰이 가능한 경우가 있지만,
  실제 장치가 내보내는 HID usage/report descriptor를 확인하고 압력·접촉 비트를
  HidP API로 해석해야 합니다. PTH-451의 보고서 형식을 추측하지 않았습니다.
  이 저장소에는 Raw HID 또는 Ink 대체 백엔드가 아직 없습니다.

압력 범위는 드라이버 DVC_NPRESSURE에서 조회하므로 2048을 하드코딩하지 않습니다.
접촉은 압력이 0보다 큰 것으로 판단합니다. 별도 tip-switch가 필요한 드라이버는 추가 구현이 필요합니다.
X/Y는 컨텍스트 출력 범위로 정규화하며 단위는 mm가 아닌 태블릿 범위/초입니다.
현재 가로·세로 물리 크기 차이를 보정하지 않으므로 방향별 질감 차이가 있을 수 있습니다.
좌표는 오디오 상태에만 사용하며 디스크에 기록하지 않습니다.

## 반드시 수행할 Windows 검증

프로그램을 새로 시작해 각 실험의 패킷 수를 비교하세요. 진단 저장 버튼은
`%LOCALAPPDATA%\PenASMR\diagnostics.json`을 작성합니다. 저장 시 덮어쓰므로
실험별 파일을 따로 보관하세요. 수치는 앱 시작 이후 누적입니다.

1. 앱 창 활성화 상태에서 펜을 움직이고 눌러 패킷·접촉·최대 필압이 증가하는지 확인.
2. **OneNote를 활성화한 채** 20초 동안 필기. 앱으로 돌아와 Background 카운터,
   Contact, Max pressure를 확인. Background는 '다른 창'을 뜻하므로 이 실험 중
   다른 앱을 사용하지 마세요. 전경 성공과 별개로 판단해야 합니다.
3. OneNote에서 가벼운/강한 압력으로 각각 쓰고 소리 크기 변화를 확인.
   실제 선이 정상적으로 그려지고 누락·필압 손실이 없는지도 확인.
4. 같은 거리를 느리게/빠르게 써서 질감 진행과 밀도 차이를 확인.
   멈춤·펜 떼기 시 꼬리 소리가 없는지 확인. 논리적 정지 감지는 최대 약 35ms,
   추가 오디오 버퍼·OS/드라이버 지연이 있어 실제 종단 지연은 측정이 필요합니다.
5. 최소화 상태에서도 1분 필기. 작업 관리자로 CPU/RAM과 OneNote 반응을 비교.
   Audio status events가 증가하면 버퍼 언더런 등을 확인하고
   `penasmr/__main__.py`의 blocksize를 256에서 512로 늘려 재검증할 수 있습니다.
6. 출력 장치를 바꿀 때는 앱을 재시작하세요. 닫기 버튼은 종료이며 트레이 기능은 없습니다.

패킷 0 또는 Background만 0이면: Wacom 드라이버 진단에서 장치 인식 확인 →
다른 Wintab 사용 앱 종료 → 앱/OneNote를 같은 일반 사용자 권한으로 재실행 →
드라이버 버전과 위 결과 기록. Wintab32.dll은 이름과 달리 실행 Python과 비트수가
맞아야 합니다. DLL 로드 오류는 드라이버/비트수 문제부터 확인하세요.
OneNote에서만 0이면 컨텍스트 배타성 가능성이 있으나 이 결과 하나로 불가능하다고
단정하지 않습니다. 다음 작업은 해당 Windows에서 Raw HID 장치 열거 및 보고서
디스크립터 검증입니다. 관리자 권한이나 Windows Ink 해제를 기본 해결책으로 요구하지 않습니다.

## 오디오 설계와 제한

외부 녹음 루프 대신 무작위 공간 종이 텍스처를 보간하고 대역을 성형합니다.
펜 속도가 텍스처의 진행 속도를, 압력이 음량 곡선을 제어합니다.
무접촉/정지/35ms 이상 입력 미수신 시 약 수 ms의 짧은 감쇠로 클릭을 줄입니다.
정지 중 텍스처 진행은 감쇠 구간에만 남습니다. 실제 거리와 샘플 단위로 완벽히
일치하는 방식은 아니며 4ms 폴링의 최신 좌표로 추정한 속도로 진행합니다.
드라이버별 노이즈와 실제 연필 같은 음색은 실기 청취·튜닝이 필요합니다.
오디오 콜백은 Python 연산이므로 하드 실시간이나 저사양 성능을 보장하지 않습니다.
48kHz mono float, 256 프레임(약 5.3ms) 요청이며 실제 장치 지연은 더 클 수 있습니다.
텍스처 메모리는 수 MB 수준이며 UI 상태 갱신은 0.5초 간격입니다.

## 개발 / 클라우드 검증

```
python -m unittest discover -s tests -v
python -m compileall -q penasmr run.py
```

Linux에서 모션/합성 테스트를 실행할 수 있습니다. Windows 입력·장치 출력은
Windows에서 위 절차로 별도 검증해야 합니다. 테스트 4개는 호버/첫 접촉,
이동 속도, 압력 에너지 변화, 정지·오래된 입력·음소거, 출력 범위를 검사합니다.
Tk와 ctypes는 Python 표준 라이브러리이며 런타임 외부 의존성은 sounddevice입니다.

## 라이선스

이 프로젝트 소스는 MIT (`LICENSE`). 외부 연필 샘플을 사용하지 않으므로 샘플
권리나 유료 서비스가 필요 없습니다. sounddevice/PortAudio는 MIT 계열이고,
EXE에는 CFFI 등 전이 의존성과 Python/Tcl/Tk도 포함될 수 있습니다.
PyInstaller는 GPL에 상용/자유 배포용 부트로더 예외를 제공합니다.
배포할 때 실제 포함된 패키지의 라이선스 고지를 보존하세요.

6초 합성 예시 파일 만들기(실제 펜 입력 검증과 별개):
`python render_demo.py /tmp/penasmr-demo.wav` (Windows에서는 `demo.wav` 경로 사용).
앞 2초는 느리고 약하게, 다음 2초는 빠르고 강하게, 마지막 2초는 정지입니다.

클라우드 설치 결과: Python 3.12에서 sounddevice 의존성 설치와 `pip check` 통과.
Linux 시스템 PortAudio가 없어 sounddevice 로딩은 실패했습니다. 이 호스트에서 실제
오디오 출력은 검증하지 못했습니다. Windows용 sounddevice 배포에는 PortAudio가
포함되지만 Windows 현장에서 실행 확인이 필요합니다. Linux WAV 렌더링은 이를 요구하지 않습니다.
