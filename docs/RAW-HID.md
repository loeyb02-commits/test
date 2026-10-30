# Raw HID 백그라운드 입력 실험

## 현재 확인된 사실

사용자 실기 결과 Wintab은 PenASMR 전경에서 좌표·필압·소리를 제공했지만 다른 창이
활성화되면 전달이 멈췄습니다. Wintab 보고서의 백그라운드 3개/접촉 2개는 큐 처리
시점의 창 상태로 분류한 전환 패킷일 수 있어 동시 수집 성공으로 판단하지 않습니다.

제공된 HID inventory에는 VID `056A` / PID `0314`의 Digitizers/Pen (`0x0d/0x02`)
컬렉션이 있습니다. 이는 표준 HID 보고서 수집을 시도할 근거이며, 수신 성공의 증거는 아닙니다.
이번 구현은 그 표준 인터페이스를 위한 **실험적 실제 입력 백엔드**입니다.

## 새 소스 빌드·실행

1. 이전 PenASMR을 모두 닫습니다. Windows Ink를 켜 둡니다.
2. GitHub의 Code → Download ZIP을 받아 새 폴더에 압축을 풉니다.
3. Python 3.13 x64가 설치된 상태에서 `build.cmd`를 실행합니다.
4. 새 폴더의 **`run-rawhid.cmd`**를 실행합니다. 창 제목이 `PenASMR — rawhid`인지 확인하세요.
   EXE를 그냥 더블클릭하면 기존 Wintab 모드입니다.
5. 처음에는 앱 자체 창에서 이동·필압·펜 떼기와 소리를 확인하고, 이어 OneNote를
   활성화하여 20초 이상 필기합니다. 그동안 다른 앱은 사용하지 않습니다.
6. PenASMR으로 돌아와 **Save diagnostic report**를 누릅니다.

PowerShell에서 직접 실행할 수도 있습니다:

```powershell
.\dist\PenASMR\PenASMR.exe --backend rawhid
```

오디오와 분리해서 입력만 시험하려면:

```powershell
.\dist\PenASMR\PenASMR.exe --backend rawhid --input-only
```

빌드 없이 소스 실행은 `run.cmd --backend rawhid` 또는 가상환경의 Python으로
`run.py --backend rawhid`를 실행합니다. 추가 Python 패키지는 필요 없습니다.
Wintab을 동시에 열거나 실패 시 몰래 Wintab으로 되돌아가지 않습니다.

## 결과 확인

탐색기 주소창에 `%LOCALAPPDATA%\PenASMR`를 입력하세요.

- `rawhid-startup.json`: 준비 단계와 실제 HID 필드/논리 범위/보고서 ID, 오류를 자동 저장.
  최신 Raw HID 모듈은 `rawhid_revision: 1`입니다. 초기화 중 실패해도 파일이 남습니다.
- `diagnostics.json`: 진단 버튼으로 저장. `input_backend`가 `rawhid`인지 확인.
  `raw_messages`, `sink_messages`, 입력·접촉·필압·백그라운드 통계 및 시작 로그 포함.

`Packets`, `Contact`, `Max pressure`가 변해야 실제 좌표·필압 해석이 된 것입니다.
OneNote에서 쓰는 동안 `Background`, `BG contact`가 지속적으로 증가하고 실제 선과
필압도 보존되어야 목적에 맞는 동시 입력으로 평가할 수 있습니다. `sink_messages`만
증가하거나 hover만 수신하는 것은 필압/접촉 성공이 아닙니다.

Raw HID의 Background는 WM_INPUT의 `RIM_INPUTSINK` 표시가 있고, 다른 전경 창이
500ms 이상 유지된 경우만 집계합니다. 전환 직후의 입력은 `transition_packets`로
따로 세므로 클릭 몇 개만으로 백그라운드 성공으로 보지 않습니다. 이 카운터가
자동으로 OneNote 프로세스를 식별하는 것은 아닙니다.

이상 동작이 있으면 닫기 버튼으로 종료하세요. 종료 시 해당 Raw Input 등록과
창 메시지 서브클래스를 제거합니다. 장치 연결 해제 시 수집을 중단하며 재연결 후
프로그램을 다시 시작해야 합니다. 실행 중 출력 장치가 바뀌어도 재시작하세요.

다음 진단에는 위 두 JSON 파일을 함께 사용합니다. 좌표/필기 내용/원시 보고서 바이트,
장치 경로나 일련번호는 기록하지 않습니다. 새 실행/저장은 기존 파일을 덮어씁니다.

## 입력 구현과 한계

- `RegisterRawInputDevices`에 `RIDEV_INPUTSINK | RIDEV_DEVNOTIFY`와 앱 HWND 전달.
  `RIDEV_NOLEGACY`, 입력 가로채기, 독점 장치 열기, 커널 드라이버 설치, Windows Ink 해제 없음.
- 수신한 RAWHID에서 실제 Wacom 펜 장치 HANDLE만 선택. VID=0의 가상 펜과
  vendor-specific 컬렉션은 같은 표준 펜이라고 가정하지 않고 제외.
- RIDI_PREPARSEDDATA를 조회하고 HidP_GetCaps/GetValueCaps/GetButtonCaps로
  실제 보고서 필드를 찾음. HidP_GetData로 데이터 인덱스에 따른 값을 읽음.
- Generic Desktop X/Y, Digitizers Tip Pressure, Tip Switch 필수. In Range가
  선언되어 있으면 함께 확인. 실제 tip·압력으로 접촉 여부 판단.
- 좌표와 필압은 HID descriptor의 논리 범위로 정규화. 필압 2048단계를 하드코딩하지 않음.
- 현재 지원 범위는 하나의 절대좌표 펜 보고서/동일 link collection에 X/Y/pressure/tip이
  있는 한 개의 Wacom 표준 펜 컬렉션. 분리 보고서/벤더 전용 형식/여러 적합 장치는
  추측으로 섞지 않고 오류를 남김. 실제 descriptor가 이 조건과 다른지는 다음 실기 로그로 확인.
- 여러 보고서가 한 WM_INPUT에 묶이면 개별 시간 정보가 없으므로 마지막 위치만 모션
  엔진에 전달. 순간 속도/거리 진행은 근사값이며 실제 지연·음색·저사양 성능은 미측정.
- 등록 성공 또는 descriptor 해석 성공은 드라이버의 실제 백그라운드 전달 보장이 아님.
  드라이버가 보고서를 전달하지 않으면 Raw Input도 성공할 수 없음.

## 클라우드 검증

Microsoft 공식 `hidpi.h`의 선언을 Windows 폭의 정수형으로 C 컴파일해 구조체
크기/오프셋을 대조했습니다. CAPS=64, VALUE_CAPS=72, BUTTON_CAPS=72, DATA=8.

합성 HID descriptor/report로 값·범위·접촉 해석, 다른 report ID 제외, 필수 필드 누락,
배치 보고서, 백그라운드 전환 제외, 등록·해제, 콜백 오류·연결 해제 중단을 검사했습니다.
기존 테스트를 포함해 **40개 통과**. 이 Linux에서는 Windows EXE 빌드, 실제 입력,
OneNote 공존 또는 오디오 출력은 검증하지 못했습니다.

참고: [Microsoft hidpi.h](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/shared/hidpi.h),
[Raw Input 등록](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerrawinputdevices),
[HidP_GetData](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/hidpi/nf-hidpi-hidp_getdata).
