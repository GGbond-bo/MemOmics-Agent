// MemOmics V5 password-only SSH_ASKPASS helper.
//
// This fixed executable reads only a short-lived, non-secret prompt-to-
// Credential-Manager-target map from the environment.  It never invokes a
// shell, writes diagnostics, or receives a password through argv/environment.
// The Python caller verifies this source's compiled hash and starts only the
// trusted Windows OpenSSH client for V5 password profiles.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

internal static class MemOmicsAskpassHelper
{
    private const int CredTypeGeneric = 1;
    private const int MaxBlob = 5 * 512;
    private const int MaxMapBytes = 8192;
    private const long MaxLifetimeSeconds = 120;
    private static readonly byte[] Magic = new byte[] { 0x4d, 0x4d, 0x43, 0x56, 0x31, 0x00 };
    private const string TargetPrefix = "MemOmics/cluster/v5/";
    private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct FILETIME { public uint dwLowDateTime; public uint dwHighDateTime; }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct CREDENTIAL
    {
        public uint Flags;
        public uint Type;
        public string TargetName;
        public string Comment;
        public FILETIME LastWritten;
        public uint CredentialBlobSize;
        public IntPtr CredentialBlob;
        public uint Persist;
        public uint AttributeCount;
        public IntPtr Attributes;
        public string TargetAlias;
        public string UserName;
    }

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CredRead(string target, uint type, uint flags, out IntPtr credential);

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern void CredFree(IntPtr credential);

    private static bool IsLowerHex(string value, int length)
    {
        if (value == null || value.Length != length) return false;
        for (int i = 0; i < value.Length; ++i)
        {
            char c = value[i];
            if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
        }
        return true;
    }

    private static bool IsTarget(string target)
    {
        if (String.IsNullOrEmpty(target) || !target.StartsWith(TargetPrefix, StringComparison.Ordinal)) return false;
        string[] parts = target.Split('/');
        if (parts.Length != 5 || parts[0] != "MemOmics" || parts[1] != "cluster" || parts[2] != "v5") return false;
        return IsLowerHex(parts[3], 32) && parts[4].Length == 20 && parts[4].StartsWith("account-", StringComparison.Ordinal)
            && IsLowerHex(parts[4].Substring(8), 12);
    }

    private static bool IsPrompt(string value)
    {
        if (String.IsNullOrEmpty(value) || value.Length > 4096) return false;
        for (int i = 0; i < value.Length; ++i)
        {
            if (Char.IsControl(value[i])) return false;
        }
        return true;
    }

    private static string NormalizePrompt(string value)
    {
        // Win32 OpenSSH 9.5 has emitted both a prompt ending immediately at
        // ':' and the same prompt with one cosmetic trailing ASCII space.
        // Normalize only that one documented variation; every other byte is
        // still an exact map key and unknown/interactive prompts fail closed.
        return value != null && value.EndsWith(" ", StringComparison.Ordinal)
            ? value.Substring(0, value.Length - 1) : value;
    }

    private static byte[] FromBase64Url(string value)
    {
        if (String.IsNullOrEmpty(value) || value.Length > (MaxMapBytes * 2)) throw new InvalidDataException();
        string normalized = value.Replace('-', '+').Replace('_', '/');
        switch (normalized.Length % 4)
        {
            case 0: break;
            case 2: normalized += "=="; break;
            case 3: normalized += "="; break;
            default: throw new InvalidDataException();
        }
        byte[] bytes = Convert.FromBase64String(normalized);
        if (bytes.Length == 0 || bytes.Length > MaxMapBytes) throw new InvalidDataException();
        return bytes;
    }

    private static int ReadU16(byte[] value, ref int offset)
    {
        if (offset + 2 > value.Length) throw new InvalidDataException();
        int result = value[offset] | (value[offset + 1] << 8);
        offset += 2;
        return result;
    }

    private static string ReadText(byte[] value, ref int offset)
    {
        int length = ReadU16(value, ref offset);
        if (length < 1 || length > 4096 || offset + length > value.Length) throw new InvalidDataException();
        string result = Utf8.GetString(value, offset, length);
        offset += length;
        return result;
    }

    private static Dictionary<string, string> ReadMap(string encoded)
    {
        byte[] bytes = FromBase64Url(encoded);
        try
        {
            int offset = 0;
            int count = bytes[offset++];
            if (count < 1 || count > 2) throw new InvalidDataException();
            var result = new Dictionary<string, string>(StringComparer.Ordinal);
            for (int index = 0; index < count; ++index)
            {
                string prompt = NormalizePrompt(ReadText(bytes, ref offset));
                string target = ReadText(bytes, ref offset);
                if (!IsPrompt(prompt) || !IsTarget(target) || result.ContainsKey(prompt)) throw new InvalidDataException();
                result.Add(prompt, target);
            }
            if (offset != bytes.Length) throw new InvalidDataException();
            return result;
        }
        finally { Array.Clear(bytes, 0, bytes.Length); }
    }

    private static long UnixNow()
    {
        return (long)Math.Floor((DateTime.UtcNow - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds);
    }

    private static bool ValidExpiry(string text)
    {
        long expiry;
        if (!Int64.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out expiry)) return false;
        long now = UnixNow();
        return expiry >= now - 2 && expiry <= now + MaxLifetimeSeconds;
    }

    private static byte[] ReadPasswordBlob(string target)
    {
        IntPtr pointer = IntPtr.Zero;
        byte[] blob = null;
        try
        {
            if (!CredRead(target, CredTypeGeneric, 0, out pointer) || pointer == IntPtr.Zero) return null;
            CREDENTIAL credential = (CREDENTIAL)Marshal.PtrToStructure(pointer, typeof(CREDENTIAL));
            if (credential.Type != CredTypeGeneric || credential.CredentialBlob == IntPtr.Zero || credential.CredentialBlobSize <= Magic.Length + 8 || credential.CredentialBlobSize > MaxBlob)
                return null;
            blob = new byte[credential.CredentialBlobSize];
            Marshal.Copy(credential.CredentialBlob, blob, 0, blob.Length);
            for (int index = 0; index < Magic.Length; ++index)
                if (blob[index] != Magic[index]) return null;
            ulong revision = BitConverter.ToUInt64(blob, Magic.Length);
            if (revision < 1) return null;
            int passwordOffset = Magic.Length + 8;
            byte[] password = new byte[blob.Length - passwordOffset];
            Buffer.BlockCopy(blob, passwordOffset, password, 0, password.Length);
            // Credential Manager can contain arbitrary Generic Credential
            // data.  Only the exact V5 UTF-8 password record is eligible for
            // stdout; malformed/control-containing blobs fail closed.
            Utf8.GetCharCount(password);
            for (int index = 0; index < password.Length; ++index)
                if (password[index] == 0 || password[index] == 10 || password[index] == 13)
                {
                    Array.Clear(password, 0, password.Length);
                    return null;
                }
            return password;
        }
        finally
        {
            if (blob != null) Array.Clear(blob, 0, blob.Length);
            if (pointer != IntPtr.Zero) CredFree(pointer);
        }
    }

    public static int Main(string[] args)
    {
        byte[] password = null;
        try
        {
            if (args == null || args.Length != 1 || !IsPrompt(args[0])) return 2;
            if (!ValidExpiry(Environment.GetEnvironmentVariable("MEMOMICS_ASKPASS_EXPIRES_UNIX"))) return 3;
            Dictionary<string, string> map = ReadMap(Environment.GetEnvironmentVariable("MEMOMICS_ASKPASS_MAP"));
            string target;
            if (!map.TryGetValue(NormalizePrompt(args[0]), out target)) return 4;
            password = ReadPasswordBlob(target);
            if (password == null || password.Length < 1) return 5;
            // SSH_ASKPASS consumes stdout.  There is deliberately no newline or diagnostic output.
            Console.OpenStandardOutput().Write(password, 0, password.Length);
            return 0;
        }
        catch { return 6; }
        finally
        {
            if (password != null) Array.Clear(password, 0, password.Length);
        }
    }
}
