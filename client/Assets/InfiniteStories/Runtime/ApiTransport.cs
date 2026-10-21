using System;
using System.Collections;
using System.Security.Cryptography;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace InfiniteStories
{
    public sealed class ApiTransport : MonoBehaviour
    {
        public string Origin { get; set; }
        public string ResumeToken
        {
            get
            {
                string token = PlayerPrefs.GetString("is.resumeToken", "");
                if (token.Length < 43)
                {
                    byte[] bytes = new byte[32];
                    using (var rng = RandomNumberGenerator.Create()) rng.GetBytes(bytes);
                    token = Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
                    PlayerPrefs.SetString("is.resumeToken", token); PlayerPrefs.Save();
                }
                return token;
            }
        }

        public IEnumerator ReadCapabilities(Action<Capabilities> success, Action failure)
        {
            using (var request = UnityWebRequest.Get(Origin.TrimEnd('/') + "/v1/capabilities"))
            {
                request.timeout = 10;
                yield return request.SendWebRequest();
                Capabilities value = null;
                if (request.result == UnityWebRequest.Result.Success && request.downloadHandler.data.Length < 16384)
                { try { value = JsonUtility.FromJson<Capabilities>(request.downloadHandler.text); } catch (ArgumentException) { } }
                if (value != null && value.schema_version == 1) success(value); else failure();
            }
        }

        public IEnumerator Send(string path, string method, string body, Action<GameView> success, Action<ApiError, bool> failure)
        {
            if (!path.StartsWith("/v1/sessions", StringComparison.Ordinal))
            { failure(new ApiError { code = "CLIENT_PATH", message = "Unsupported journey request." }, false); yield break; }
            string token = null;
            try { token = ResumeToken; }
            catch (CryptographicException) { }
            catch (PlatformNotSupportedException) { }
            if (string.IsNullOrEmpty(token))
            { failure(new ApiError { code = "SECURE_SESSION_UNAVAILABLE", message = "This browser could not create a secure journey credential. No request was sent." }, false); yield break; }
            using (var request = new UnityWebRequest(Origin.TrimEnd('/') + path, method))
            {
                request.downloadHandler = new DownloadHandlerBuffer();
                if (!string.IsNullOrEmpty(body)) request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
                request.SetRequestHeader("Content-Type", "application/json");
                request.SetRequestHeader("Authorization", "Bearer " + token);
                request.timeout = 65; // Server's model turn is bounded to 45 seconds.
                yield return request.SendWebRequest();
                if (request.result != UnityWebRequest.Result.Success)
                {
                    ApiError error = null;
                    try { error = JsonUtility.FromJson<ErrorEnvelope>(request.downloadHandler.text)?.error; } catch (ArgumentException) { }
                    failure(error ?? new ApiError { code = "NETWORK_UNAVAILABLE", message = "The journey service could not be reached. Your last confirmed save is safe." }, request.responseCode == 0 || request.responseCode >= 500);
                    yield break;
                }
                GameView view = null;
                bool invalid = false;
                try
                {
                    if (request.downloadHandler.data.Length > 1048576) throw new ArgumentException("Oversized save.");
                    view = JsonUtility.FromJson<GameView>(request.downloadHandler.text);
                    if (view == null || view.schema_version != 1 || view.state == null || view.state.schema_version != 1 ||
                        view.location == null || view.objectives == null || view.nearby == null || string.IsNullOrEmpty(view.session_id))
                        throw new ArgumentException("Unsupported save.");
                    view.location.Validate();
                }
                catch (ArgumentException)
                { invalid = true; }
                if (invalid)
                { failure(new ApiError { code = "SAVE_INVALID", message = "This save response could not be safely loaded." }, true); yield break; }
                success(view);
            }
        }
    }
}
