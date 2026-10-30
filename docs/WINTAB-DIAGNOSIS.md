# WTOpen 초기화 수정과 Windows 재검증

## 이번에 확인된 원인과 아직 확인되지 않은 원인

이전 `WTOpenW failed: driver rejected background context`는 프로그램이 만든 문구입니다.
API가 NULL을 반환했다는 사실만 확인하며, '백그라운드라서 거부했다'는 근거가 아닙니다.
기존 오류 설명이 원인을 단정한 부분을 수정했습니다.

공식 Wacom SDK 헤더/예제와 기존 코드를 대조한 결과:

| 항목 | 분석 및 수정 |
| --- | --- |
| LOGCONTEXTW 필드 순서/정수 폭 | 기존 Windows 선언은 일치. W는 212바이트, A는 172바이트, AXIS는 16바이트. x64에서도 LONG/UINT는 4바이트, HANDLE만 포인터 크기. |
| WCHAR | Windows에서는 기존 c_wchar가 2바이트로 맞지만 Linux에서는 4바이트. 수정본은 UTF-16 40개를 명시하여 다른 OS에서도 Windows ABI 자체를 검사 가능. |
| 패킷 | X/Y는 LONG, 절대 압력은 UINT, 순서는 마스크 비트 순서, 크기는 12바이트. 요구 마스크는 0x580. |
| CXO_PEN | 기존 코드가 강제로 추가. 단순 펜 감지/백그라운드 구독 플래그가 아니므로 제거. 이 옵션이 해당 PC에서 실제 거부 원인이었는지는 새 로그 및 실기 비교 전에는 확정 불가. |
| CXO_SYSTEM | 백그라운드 구독 플래그가 아님. 기본 시스템 컨텍스트의 값을 유지하고, 대체 digitizer 컨텍스트에서는 해제. 커서 매핑 영역은 변경하지 않음. |
| HWND | Tk 자식 HWND 대신 GA_ROOT로 실제 최상위 HWND를 찾고 IsWindow로 확인. 기존 HWND가 잘못되었는지는 이전 로그 부재로 미확정. |
| WTInfo | 크기를 먼저 확인하고 정확한 ABI와 일치하는 경우에만 읽음. 장치의 DVC_PKTDATA에서 X/Y/pressure 지원 및 축 범위 확인. |
| 생성/활성화 | 기존 즉시 활성화 대신 비활성 생성 → WTOverlap(FALSE) → WTEnable(TRUE) → 다시 WTOverlap(FALSE). 우선순위 내리기 실패 시 닫음. TRUE로 승격하지 않음. |
| 버튼 캡처 | 기본값에서 이어받은 버튼 마스크를 둘 다 0으로 설정해 명시적 버튼 이벤트 처리 및 암묵적 버튼 캡처를 요청하지 않음. |
| 드라이버 협상 결과 | WTGetW/A로 실제 출력 범위·패킷 형식 확인. 형식이 바뀌면 패킷을 잘못 해석하지 않고 닫음. |
| ANSI 호환 | W 시스템 → W digitizer → A 시스템 → A digitizer 순서의 최대 4회 시도. 각 API에 맞는 구조체를 사용하며, 실패한 컨텍스트는 다음 시도 전에 닫음. |

WTOpen에 SetLastError 지원이 보장되지 않으므로 **last_error=0도 실패 원인 없음/성공을
의미하지 않습니다.** 비영 값도 부가 정보로만 기록하며, 이것만으로 권한 문제를 단정하지 않습니다.
기존 구현에는 이 값이나 전달 설정이 기록되지 않아 과거 실행의 정확한 거부 원인을
소급 확정할 수 없습니다. 수정본도 물리 장치에서 성공했다고 주장하지 않습니다.

공식 대조 자료(검사한 SDK commit: `8c8fe264697a2720c2679c046c0c016a18990a45`):

- [WINTAB.H](https://github.com/Wacom-Developer/wacom-device-kit-windows/blob/8c8fe264697a2720c2679c046c0c016a18990a45/WintabSDK/WINTAB.H)
- [PKTDEF.H](https://github.com/Wacom-Developer/wacom-device-kit-windows/blob/8c8fe264697a2720c2679c046c0c016a18990a45/WintabSDK/PKTDEF.H)
- [공식 ScribbleDemo](https://github.com/Wacom-Developer/wacom-device-kit-windows/blob/8c8fe264697a2720c2679c046c0c016a18990a45/Wintab%20ScribbleDemo/SampleCode/ScribbleDemo.CPP)

## Windows에서 다시 빌드

1. 실행 중인 이전 PenASMR을 모두 닫습니다. Windows Ink는 켜 둡니다.
2. GitHub 저장소의 **Code → Download ZIP**으로 최신 소스를 받고, 이전 폴더와 다른
   새 폴더에 압축을 풉니다. 예전 EXE 바로가기를 실행하지 않도록 주의합니다.
3. Python 3.13 x64가 설치된 상태에서 새 폴더의 `build.cmd`를 실행합니다.
   자동 테스트가 끝난 뒤 PyInstaller가 새 EXE를 만듭니다. 테스트 실패 시 빌드하지 않습니다.
4. `dist\PenASMR\PenASMR.exe`를 실행합니다. EXE만 다른 폴더로 옮기지 마세요.

먼저 오디오와 무관한 입력 검사를 하려면 소스 폴더에서 PowerShell을 열어 실행합니다:

```powershell
.\dist\PenASMR\PenASMR.exe --input-only
```

또는 빌드 없이(가상환경 설치 완료 후):

```powershell
.\.venv\Scripts\python.exe run.py --input-only
```

`--input-only`는 오디오 장치를 열지 않습니다. Wintab 초기화/패킷 검증을 먼저 하고,
통과한 뒤 인자 없이 실행해 사운드까지 확인합니다.

## 오류 발생 시 자동으로 남는 파일

Windows 탐색기 주소창에 `%LOCALAPPDATA%\PenASMR`를 입력하세요.

- `wintab-startup.json`: 초기화 중 매 단계 자동 저장. GUI 진단 버튼을 누르기 전
  실패해도 남습니다. 새 실행 시 덮어쓰므로 실행별로 복사해 보관하세요.
- `diagnostics.json`: 앱의 **Save diagnostic report** 버튼으로 저장. 시작 로그와
  전경/백그라운드/접촉 패킷 통계 및 오류 목록을 포함합니다.

로그에는 Python/포인터 크기, 구조체 크기, HWND 유효성, 기본 컨텍스트 전체 필드,
요청 컨텍스트 전체 필드, 지원 옵션/패킷 마스크, 축 범위, 각 API 반환값/Win32
last-error, WTGet 실제 컨텍스트, 실패 단계가 들어갑니다. 펜 좌표, 필기 내용,
다른 창 제목은 기록하지 않습니다. 로그 저장 실패 시 초기화 오류에 그 사유도 표시합니다.

로그 읽는 기준:

- `WTInfo ... size ..., expected ...`: 구조체/Unicode 지원 또는 정보 조회 단계 문제.
  W가 실패하고 A가 열리면 Unicode 경로 차이를 의심할 수 있습니다.
- `Device lacks required ...`: 장치가 요청된 패킷 기능을 보고하지 않음. 압력 0을
  가짜 값으로 채우거나 마우스 좌표로 대체하지 않습니다.
- `WTOpenW/A`의 `result: 0`: 요청을 열지 못함. 바로 앞 `open_attempt` 설정과
  `last_error`를 함께 확인합니다. 정확한 드라이버 내부 사유는 여전히 미보고일 수 있습니다.
- `WTOverlap(FALSE)` 실패: 타 앱 입력 우선순위를 보호할 수 없어 중단.
- `context_opened`: 생성/설정 협상만 성공. 패킷 수신 또는 OneNote 동시 수집 성공은 아님.
- 시작은 성공하지만 Background/BG contact가 0: OneNote를 활성화한 상태의
  Wintab 전달이 안 되는지 별도 진단 필요. 입력이 없으면 소리는 중지 상태를 유지합니다.

## OneNote 동시 입력 검증

1. 앱을 새로 시작하여 자체 창에서 펜 이동/접촉 시 Packets, Contact, Max pressure가
   증가하는지 확인합니다. 이 결과는 전경 검사로만 기록합니다.
2. OneNote로 전환해 20초간 씁니다. **그동안 다른 앱은 사용하지 않습니다.**
   선/필압/버튼 동작이 정상인지 확인한 다음 PenASMR으로 돌아와 Background와
   BG contact가 둘 다 늘었는지 확인하고 진단 보고서를 저장합니다.
3. `--input-only`를 종료하고 인자 없이 실행하여 소리와 필기 동시 동작을 확인합니다.
   최소화, 펜 떼기, 정지, 느린/빠른 이동, 약한/강한 필압도 각각 확인합니다.
4. OneNote 입력이 달라지거나 선이 누락되면 PenASMR을 종료하고 해당 결과를 기록하세요.
   컨텍스트를 뒤로 보내고 버튼 캡처를 제거해도 드라이버 전체 동작을 보장할 수는 없습니다.

전경에서만 수신되면 성공으로 처리하지 않습니다. Background 카운터는 '다른 창'을
뜻하므로 OneNote 실험 조건을 지킨 결과와 함께 판단합니다. 수정본은 전역 훅,
입력 재주입, WTOverlap(TRUE), 드라이버 설정 변경, Windows Ink 해제를 사용하지 않습니다.
Wintab은 독립적인 수동 복제 스트림을 보장하지 않아 컨텍스트를 맨 아래로 보내면
상위 컨텍스트에 가려져 패킷이 없을 수 있습니다. 이 제한을 우선순위 승격으로 우회하지 않습니다.

## Raw HID 대체 가능성 확인

Wintab 생성이나 동시 전달이 계속 실패하면 다음 명령으로 **조회 전용** Raw Input
HID 목록을 저장할 수 있습니다. Wintab DLL과 오디오 장치를 열지 않습니다.

```powershell
.\dist\PenASMR\PenASMR.exe --hid-info
```

결과는 `%LOCALAPPDATA%\PenASMR\hid-inventory.json`입니다.
Wacom vendor ID는 1386 (`0x056a`), Digitizers usage page는 13 (`0x0d`)입니다.
와콤 장치라도 vendor-specific usage만 보이거나, 드라이버가 펜 인터페이스를 Raw Input에
노출하지 않을 수 있습니다. 목록에 장치가 보이는 것과 실제 보고서를 읽는 것은 별개입니다.
이 도구는 장치 등록·캡처·독점 열기를 하지 않으며 **Raw HID 입력 백엔드는 아닙니다.**

실제 대체 백엔드를 구현하려면 해당 PC에서 다음을 검증해야 합니다:

1. GetRawInputDeviceList/Info로 적절한 top-level collection 식별. 마우스로만
   노출되면 Raw Input 마우스 패킷으로 실제 필압을 얻을 수 없습니다.
2. RIDEV_INPUTSINK와 숨은 HWND로 해당 HID collection을 등록하고 WM_INPUT 수신.
   RIDEV_NOLEGACY/독점 장치 열기/Windows Ink 설정 변경은 사용하지 않습니다.
3. RIDI_PREPARSEDDATA와 HidP_GetCaps/GetValueCaps/GetButtonCaps로 report ID,
   X/Y logical 범위, pressure, tip switch, in-range를 해석. 표준 Digitizers의
   Tip Pressure=0x30, Tip Switch=0x42이지만 vendor report에는 임의로 적용하지 않습니다.
4. OneNote가 전경인 동안 실제 보고서와 변화하는 압력/접촉 비트가 함께 들어오고,
   OneNote 선/압력이 보존되는지 별도 검증. 장치 연결 해제/재연결도 처리.

Raw HID도 드라이버가 데이터를 숨기거나 독점 처리하면 이용이 제한됩니다. 현재는
장치 보고서/디스크립터가 없어 PTH-451용 보고서 형식을 추측해 자동 대체하지 않았습니다.
다음 진단에는 `wintab-startup.json`, 실험 후 `diagnostics.json`, 필요하면
`hid-inventory.json`, Wacom 드라이버 버전을 함께 사용합니다.

## 이 클라우드에서 검증한 것

- Wacom 공식 헤더의 A/W 선언을 Windows 폭의 정수형으로 C 컴파일하여 크기/오프셋 대조.
- 기존 엔진 테스트 + 모의 드라이버/ABI/실패 정리/ANSI fallback/Raw Input 조회 테스트 통과.
- 실제 Wintab DLL, Windows 11, Wacom, OneNote 및 EXE 빌드/출력은 이 Linux에서 미검증.

모의 드라이버 검사는 실패 분기와 호출 순서를 검증하며 하드웨어 성공의 증거가 아닙니다.
