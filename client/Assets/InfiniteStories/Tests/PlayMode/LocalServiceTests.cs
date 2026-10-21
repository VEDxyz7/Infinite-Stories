using System;
using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using UnityEngine.Tilemaps;
using UnityEngine.TestTools;

namespace InfiniteStories.Tests
{
    // Opt-in integration against the real local FastAPI process, never a provider mock.
    public sealed class LocalServiceTests
    {
        [UnityTest] public IEnumerator AuthoredJourneyRendersSavesAndResumesAcrossClientRestart()
        {
            if (Environment.GetEnvironmentVariable("IS_UNITY_HTTP_TESTS") != "1")
                Assert.Ignore("Requires the real local service on 127.0.0.1:8042 and explicit opt-in.");
            string[] keys = { "is.resumeToken", "is.sessionId", "is.pendingRequest" };
            string[] previous = Array.ConvertAll(keys, key => PlayerPrefs.GetString(key, ""));
            foreach (string key in keys) PlayerPrefs.DeleteKey(key);
            var settings = ScriptableObject.CreateInstance<ClientSettings>();
            settings.apiOrigin = Environment.GetEnvironmentVariable("IS_UNITY_TEST_API_URL") ?? "http://127.0.0.1:8042";
            GameObject root = null;
            string session = null, token = null;
            try
            {
                root = new GameObject("Real local service integration");
                root.AddComponent<GameClient>().settings = settings;
                yield return null;
                var ui = root.GetComponent<GameUI>();
                var world = root.GetComponent<TileWorld>();
                ui.StartAuthored.Invoke();
                float deadline = Time.realtimeSinceStartup + 10;
                while (world.Player == null && Time.realtimeSinceStartup < deadline) yield return null;
                Assert.IsNotNull(world.Player, "The real service response must create the Tilemap world.");
                Assert.IsFalse(ui.TitleVisible);
                Assert.AreEqual("quay", world.LocationId);
                Assert.AreEqual(2, root.GetComponentsInChildren<Tilemap>().Length);
                session = PlayerPrefs.GetString("is.sessionId");
                token = root.GetComponent<ApiTransport>().ResumeToken;
                Assert.IsFalse(string.IsNullOrEmpty(session));

                yield return null;
                var controller=root.GetComponent<GameClient>();
                // Browser controls must release Unity's text-field focus. The DOM
                // focus change alone does not deselect the uGUI input field.
                var field=root.GetComponentInChildren<InputField>();
                Assert.IsNotNull(field);
                EventSystem.current.SetSelectedGameObject(field.gameObject);
                yield return null;
                yield return null; // uGUI activates selected fields in LateUpdate.
                Assert.IsTrue(field.isFocused);
                Assert.IsTrue(ui.TextFocused);
                controller.OnBrowserCommand("north");
                Assert.IsFalse(ui.TextFocused,"Browser command must end uGUI text focus immediately.");
                yield return null;
                Assert.IsFalse(ui.TextFocused,"Text focus must remain released after input update.");
                yield return new WaitForSecondsRealtime(1.5f);
                Assert.Greater(world.Player.Position.y,5.5f,"Accessible movement must reach the real physics controller.");
                controller.OnBrowserCommand("pause");
                Assert.IsTrue(ui.Blocking);
                Vector2 paused=world.Player.Position;
                controller.OnBrowserCommand("east");
                yield return new WaitForSecondsRealtime(.4f);
                Assert.That(Vector2.Distance(world.Player.Position,paused),Is.LessThan(.01f));
                controller.OnBrowserCommand("continue");
                Assert.IsFalse(ui.Blocking);

                // A legal local movement is saved through GameClient's actual autosave path.
                world.Player.Restore(6, 5);
                yield return new WaitForSecondsRealtime(2);
                Assert.IsFalse(root.GetComponent<GameClient>().HasPending);
                ui.ReturnTitle.Invoke();
                deadline = Time.realtimeSinceStartup + 5;
                while (!ui.TitleVisible && Time.realtimeSinceStartup < deadline) yield return null;
                Assert.IsTrue(ui.TitleVisible);
                UnityEngine.Object.Destroy(root);
                yield return null;

                root = new GameObject("Restarted real local service client");
                root.AddComponent<GameClient>().settings = settings;
                yield return null;
                ui = root.GetComponent<GameUI>(); world = root.GetComponent<TileWorld>();
                ui.Resume.Invoke();
                deadline = Time.realtimeSinceStartup + 10;
                while (world.Player == null && Time.realtimeSinceStartup < deadline) yield return null;
                Assert.IsNotNull(world.Player, "Resume must load actual persisted state.");
                Assert.AreEqual(session, PlayerPrefs.GetString("is.sessionId"));
                Assert.That(Vector2.Distance(world.Player.Position, new Vector2(6, 5)), Is.LessThan(.05f));
                Assert.IsFalse(ui.TitleVisible);

                // Use real HTTP for bounded legal route setup, then the same
                // controller commands as the Web controls for choices/travel.
                // This exercises rendering/normalization, not browser input.
                controller=root.GetComponent<GameClient>();
                var api=root.GetComponent<ApiTransport>();
                GameView confirmed=null;
                yield return Read(api,session,v=>confirmed=v);
                string[] residents={"mara","ivo","sera","beacon"};
                string[] choices={"take_map","learn_rhythm","promise_guard","light_together"};
                for (int stage=0;stage<residents.Length;stage++)
                {
                    ui.ShowPause();
                    yield return Route(api,confirmed,14,9,v=>confirmed=v);
                    yield return Reload(controller,ui,world,new Vector2(14,9));
                    controller.OnBrowserCommand("choose:"+residents[stage]+":"+choices[stage]);
                    yield return Settle(controller);
                    yield return Read(api,session,v=>confirmed=v);
                    Assert.Contains(choices[stage],confirmed.state.choices,
                        "The controller choice must be confirmed by the real server.");
                    if (stage==3) break;
                    ui.ShowPause();
                    yield return Route(api,confirmed,29,8,v=>confirmed=v);
                    yield return Reload(controller,ui,world,new Vector2(29,8));
                    controller.OnBrowserCommand("travel:"+confirmed.state.location_id+"_east");
                    yield return Settle(controller);
                    yield return Read(api,session,v=>confirmed=v);
                    Assert.AreEqual(stage+2,confirmed.state.visits);
                    Assert.AreEqual(confirmed.state.location_id,world.LocationId);
                }
                Assert.AreEqual("together",confirmed.state.ending);
                Assert.IsTrue(Array.TrueForAll(confirmed.objectives,o=>o.completed));
                Assert.IsTrue(ui.Blocking,"The actual client must display its ending overlay.");
                controller.OnBrowserCommand("title");
                yield return null;
                Assert.IsTrue(ui.TitleVisible);
                controller.OnBrowserCommand("resume");
                deadline=Time.realtimeSinceStartup+10;
                while (ui.TitleVisible && Time.realtimeSinceStartup<deadline) yield return null;
                Assert.IsFalse(ui.TitleVisible);
                Assert.IsTrue(ui.Blocking,"The persisted ending must return on resume.");

                using (var request = UnityWebRequest.Delete(settings.apiOrigin + "/v1/sessions/" + session))
                {
                    request.SetRequestHeader("Authorization", "Bearer " + token);
                    yield return request.SendWebRequest();
                    Assert.AreEqual(200, request.responseCode, "Revoke the integration journey.");
                }
            }
            finally
            {
                if (root != null) UnityEngine.Object.Destroy(root);
                UnityEngine.Object.Destroy(settings);
                for (int i = 0; i < keys.Length; i++)
                {
                    if (previous[i].Length == 0) PlayerPrefs.DeleteKey(keys[i]);
                    else PlayerPrefs.SetString(keys[i], previous[i]);
                }
                PlayerPrefs.Save();
            }
        }

        static IEnumerator Read(ApiTransport api,string session,Action<GameView> accept)
        {
            yield return api.Send("/v1/sessions/"+session,"GET",null,accept,
                (error,_)=>Assert.Fail("Real local service rejected read: "+error.code));
        }
        static IEnumerator Settle(GameClient controller)
        {
            yield return null;
            float deadline=Time.realtimeSinceStartup+10;
            while (controller.HasPending && Time.realtimeSinceStartup<deadline) yield return null;
            Assert.IsFalse(controller.HasPending,"Real service action must be confirmed.");
        }
        static IEnumerator Reload(GameClient controller,GameUI ui,TileWorld world,Vector2 position)
        {
            controller.OnBrowserCommand("resume");
            float deadline=Time.realtimeSinceStartup+10;
            while ((ui.Blocking || Vector2.Distance(world.Player.Position,position)>.05f) && Time.realtimeSinceStartup<deadline)
                yield return null;
            Assert.IsFalse(ui.Blocking);
            Assert.That(Vector2.Distance(world.Player.Position,position),Is.LessThan(.05f));
        }
        static IEnumerator Route(ApiTransport api,GameView view,float x,float y,Action<GameView> accept)
        {
            // The server validates every segment. No local flags, quests, or
            // world state are fabricated; direct setup is confined to this test.
            Vector2[] points={new Vector2(view.state.x,8),new Vector2(x,8),new Vector2(x,y)};
            foreach (Vector2 point in points)
            {
                while (Vector2.Distance(new Vector2(view.state.x,view.state.y),point)>.01f)
                {
                    Vector2 next=Vector2.MoveTowards(new Vector2(view.state.x,view.state.y),point,3);
                    var request=new ActionRequest { request_id=Guid.NewGuid().ToString(),expected_revision=view.revision,
                        command=new Command { kind="position",x=next.x,y=next.y } };
                    yield return api.Send("/v1/sessions/"+view.session_id+"/actions","POST",JsonUtility.ToJson(request),v=>view=v,
                        (error,_)=>Assert.Fail("Real local service rejected route: "+error.code));
                }
            }
            accept(view);
        }
    }
}
