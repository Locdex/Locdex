use std::env;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

fn capabilities() {
    println!(
        "{{\"backend\":\"windows-native\",\"process_isolation\":true,\"filesystem_isolation\":false,\"network_isolation\":false}}"
    );
}

fn parse_run(args: &[String]) -> Result<(PathBuf, PathBuf, String, Vec<String>), String> {
    let mut workspace: Option<PathBuf> = None;
    let mut cwd: Option<PathBuf> = None;
    let mut mode = String::from("workspace-write");
    let mut index = 0usize;

    while index < args.len() {
        match args[index].as_str() {
            "--workspace" => {
                index += 1;
                workspace = args.get(index).map(PathBuf::from);
            }
            "--cwd" => {
                index += 1;
                cwd = args.get(index).map(PathBuf::from);
            }
            "--mode" => {
                index += 1;
                mode = args
                    .get(index)
                    .cloned()
                    .ok_or_else(|| String::from("--mode requires a value"))?;
            }
            "--" => {
                let command = args[index + 1..].to_vec();
                if command.is_empty() {
                    return Err(String::from("sandbox run requires a command after --"));
                }
                let workspace =
                    workspace.ok_or_else(|| String::from("--workspace is required"))?;
                let cwd = cwd.ok_or_else(|| String::from("--cwd is required"))?;
                return Ok((workspace, cwd, mode, command));
            }
            other => return Err(format!("unknown sandbox argument: {other}")),
        }
        index += 1;
    }

    Err(String::from("sandbox run requires -- followed by a command"))
}

fn canonical_inside(workspace: &Path, cwd: &Path) -> Result<(PathBuf, PathBuf), String> {
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("could not resolve workspace: {error}"))?;
    let working = cwd
        .canonicalize()
        .map_err(|error| format!("could not resolve cwd: {error}"))?;
    if !working.starts_with(&root) {
        return Err(String::from("sandbox cwd must remain inside the workspace"));
    }
    Ok((root, working))
}

#[cfg(windows)]
mod windows {
    use super::canonical_inside;
    use std::ffi::OsStr;
    use std::iter::once;
    use std::os::windows::ffi::OsStrExt;
    use std::path::{Path, PathBuf};
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::Security::{
        CreateRestrictedToken, OpenProcessToken, DISABLE_MAX_PRIVILEGE,
        TOKEN_ASSIGN_PRIMARY, TOKEN_DUPLICATE, TOKEN_QUERY,
    };
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, SetInformationJobObject,
        JobObjectExtendedLimitInformation, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    use windows_sys::Win32::System::Threading::{
        CreateProcessWithTokenW, GetCurrentProcess, GetExitCodeProcess,
        ResumeThread, WaitForSingleObject, CREATE_SUSPENDED, LOGON_WITH_PROFILE,
        PROCESS_INFORMATION, STARTUPINFOW, INFINITE,
    };

    struct Handle(HANDLE);

    impl Drop for Handle {
        fn drop(&mut self) {
            if self.0 != 0 {
                unsafe {
                    CloseHandle(self.0);
                }
            }
        }
    }

    fn wide(value: &OsStr) -> Vec<u16> {
        value.encode_wide().chain(once(0)).collect()
    }

    fn quote_arg(value: &str) -> String {
        if !value.is_empty()
            && !value.chars().any(|ch| ch.is_whitespace() || ch == '"')
        {
            return value.to_string();
        }

        let mut out = String::from("\"");
        let mut slashes = 0usize;
        for ch in value.chars() {
            if ch == '\\' {
                slashes += 1;
                continue;
            }
            if ch == '"' {
                out.push_str(&"\\".repeat(slashes * 2 + 1));
                out.push('"');
                slashes = 0;
                continue;
            }
            out.push_str(&"\\".repeat(slashes));
            slashes = 0;
            out.push(ch);
        }
        out.push_str(&"\\".repeat(slashes * 2));
        out.push('"');
        out
    }

    fn command_line(command: &[String]) -> Vec<u16> {
        let joined = command
            .iter()
            .map(|part| quote_arg(part))
            .collect::<Vec<_>>()
            .join(" ");
        wide(OsStr::new(&joined))
    }

    fn restricted_token() -> Result<Handle, String> {
        unsafe {
            let mut source: HANDLE = 0;
            let access = TOKEN_ASSIGN_PRIMARY | TOKEN_DUPLICATE | TOKEN_QUERY;
            if OpenProcessToken(GetCurrentProcess(), access, &mut source) == 0 {
                return Err(String::from("OpenProcessToken failed"));
            }
            let source = Handle(source);

            let mut restricted: HANDLE = 0;
            if CreateRestrictedToken(
                source.0,
                DISABLE_MAX_PRIVILEGE,
                0,
                std::ptr::null(),
                0,
                std::ptr::null(),
                0,
                std::ptr::null(),
                &mut restricted,
            ) == 0
            {
                return Err(String::from("CreateRestrictedToken failed"));
            }
            Ok(Handle(restricted))
        }
    }

    fn create_job() -> Result<Handle, String> {
        unsafe {
            let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if job == 0 {
                return Err(String::from("CreateJobObjectW failed"));
            }
            let job = Handle(job);
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION =
                std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags =
                JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let ok = SetInformationJobObject(
                job.0,
                JobObjectExtendedLimitInformation,
                &mut info as *mut _ as *mut _,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );
            if ok == 0 {
                return Err(String::from("SetInformationJobObject failed"));
            }
            Ok(job)
        }
    }

    pub fn run(
        workspace: PathBuf,
        cwd: PathBuf,
        _mode: String,
        command: Vec<String>,
    ) -> Result<u32, String> {
        let (_workspace, cwd) = canonical_inside(&workspace, &cwd)?;
        let token = restricted_token()?;
        let job = create_job()?;
        let mut command_line = command_line(&command);
        let cwd_wide = wide(cwd.as_os_str());

        unsafe {
            let mut startup: STARTUPINFOW = std::mem::zeroed();
            startup.cb = std::mem::size_of::<STARTUPINFOW>() as u32;
            let mut process: PROCESS_INFORMATION = std::mem::zeroed();

            let ok = CreateProcessWithTokenW(
                token.0,
                LOGON_WITH_PROFILE,
                std::ptr::null(),
                command_line.as_mut_ptr(),
                CREATE_SUSPENDED,
                std::ptr::null(),
                cwd_wide.as_ptr(),
                &startup,
                &mut process,
            );
            if ok == 0 {
                return Err(String::from("CreateProcessWithTokenW failed"));
            }

            let process_handle = Handle(process.hProcess);
            let thread_handle = Handle(process.hThread);

            if AssignProcessToJobObject(job.0, process_handle.0) == 0 {
                return Err(String::from("AssignProcessToJobObject failed"));
            }
            if ResumeThread(thread_handle.0) == u32::MAX {
                return Err(String::from("ResumeThread failed"));
            }
            WaitForSingleObject(process_handle.0, INFINITE);

            let mut exit_code = 1u32;
            if GetExitCodeProcess(process_handle.0, &mut exit_code) == 0 {
                return Err(String::from("GetExitCodeProcess failed"));
            }
            Ok(exit_code)
        }
    }
}

#[cfg(not(windows))]
mod windows {
    use std::path::PathBuf;

    pub fn run(
        _workspace: PathBuf,
        _cwd: PathBuf,
        _mode: String,
        _command: Vec<String>,
    ) -> Result<u32, String> {
        Err(String::from(
            "locdex-windows-sandbox can only execute commands on Windows",
        ))
    }
}

fn main() -> ExitCode {
    let args = env::args().skip(1).collect::<Vec<_>>();
    match args.first().map(String::as_str) {
        Some("capabilities") => {
            capabilities();
            ExitCode::SUCCESS
        }
        Some("run") => match parse_run(&args[1..]) {
            Ok((workspace, cwd, mode, command)) => {
                match windows::run(workspace, cwd, mode, command) {
                    Ok(code) => ExitCode::from((code.min(255)) as u8),
                    Err(error) => {
                        eprintln!("locdex windows sandbox: {error}");
                        ExitCode::FAILURE
                    }
                }
            }
            Err(error) => {
                eprintln!("locdex windows sandbox: {error}");
                ExitCode::FAILURE
            }
        },
        _ => {
            eprintln!(
                "usage: locdex-windows-sandbox capabilities | run --workspace PATH --cwd PATH --mode MODE -- COMMAND..."
            );
            ExitCode::FAILURE
        }
    }
}
