using System;
using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace InfiniteStories.Tests
{
    // Actual Unity HTTP against a production backend with explicitly labelled
    // captured-response HTTP replay. This is NOT live-provider verification.
    public sealed class CulturalServiceTests
    {
        [UnityTest] public IEnumerator ComparisonSwitchesSeparateSavedRunsAndReturnsWithoutChangingProgress()
        {
            if(Environment.GetEnvironmentVariable("IS_UNITY_HTTP_TESTS")!="1"||Environment.GetEnvironmentVariable("IS_UNITY_CULTURAL_TESTS")!="1")Assert.Ignore("Requires captured-only local verification service.");
            string[] keys={"is.resumeToken","is.sessionId","is.pendingRequest","is.comparison.authored","is.comparison.cultural","is.comparison.generic_control"};
            string[] prior=Array.ConvertAll(keys,k=>PlayerPrefs.GetString(k,""));foreach(string key in keys)PlayerPrefs.DeleteKey(key);
            var settings=ScriptableObject.CreateInstance<ClientSettings>();settings.apiOrigin=Environment.GetEnvironmentVariable("IS_UNITY_TEST_API_URL");
            GameObject root=null;
            try{
                root=new GameObject("Mode isolation HTTP");root.AddComponent<GameClient>().settings=settings;yield return null;
                var ui=root.GetComponent<GameUI>();var client=root.GetComponent<GameClient>();var api=root.GetComponent<ApiTransport>();
                float deadline=Time.realtimeSinceStartup+10;while(!ui.CulturalAvailable&&Time.realtimeSinceStartup<deadline)yield return null;
                Assert.IsTrue(ui.CulturalAvailable);ui.AddBrowserInterest(new Interest{name="David Bowie",category="artist"});ui.StartCultural.Invoke();
                deadline=Time.realtimeSinceStartup+10;while((ui.TitleVisible||client.HasPending)&&Time.realtimeSinceStartup<deadline)yield return null;
                string cultural=PlayerPrefs.GetString("is.sessionId");Assert.IsNotEmpty(cultural);
                GameView original=null;yield return api.Send("/v1/sessions/"+cultural,"GET",null,v=>original=v,(e,_)=>Assert.Fail(e.code));
                Assert.AreEqual("cultural",original.state.mode);string saved=JsonUtility.ToJson(original.state);
                // Simulate upgrading from the old one-slot client, then starting
                // control directly from title without first resuming the save.
                PlayerPrefs.DeleteKey("is.comparison.cultural");PlayerPrefs.Save();
                UnityEngine.Object.Destroy(root);yield return null;
                root=new GameObject("Legacy comparison bookmark");root.AddComponent<GameClient>().settings=settings;yield return null;
                ui=root.GetComponent<GameUI>();client=root.GetComponent<GameClient>();api=root.GetComponent<ApiTransport>();
                ui.StartControl.Invoke();
                deadline=Time.realtimeSinceStartup+10;while((PlayerPrefs.GetString("is.sessionId")==cultural||client.HasPending)&&Time.realtimeSinceStartup<deadline)yield return null;
                string control=PlayerPrefs.GetString("is.sessionId");Assert.AreNotEqual(cultural,control);
                GameView synthetic=null;yield return api.Send("/v1/sessions/"+control,"GET",null,v=>synthetic=v,(e,_)=>Assert.Fail(e.code));
                Assert.AreEqual("generic_control",synthetic.state.mode);Assert.AreEqual("synthetic-control-v1",synthetic.state.generic_control.version);Assert.AreEqual("none",synthetic.state.cultural_source);Assert.IsTrue(synthetic.state.cultural_context?.links==null||synthetic.state.cultural_context.links.Length==0);
                ui.ShowScanner();Assert.That(ui.ActivePanelText,Does.Contain("SYNTHETIC CONTROL"));ui.ToggleScannerComparison();
                deadline=Time.realtimeSinceStartup+10;while(PlayerPrefs.GetString("is.sessionId")!=cultural&&Time.realtimeSinceStartup<deadline)yield return null;
                Assert.AreEqual(cultural,PlayerPrefs.GetString("is.sessionId"));GameView restored=null;
                yield return api.Send("/v1/sessions/"+cultural,"GET",null,v=>restored=v,(e,_)=>Assert.Fail(e.code));
                Assert.AreEqual(saved,JsonUtility.ToJson(restored.state));Assert.AreEqual(original.revision,restored.revision);
                ui.ShowGame(restored);client.OnBrowserCommand("compare");
                deadline=Time.realtimeSinceStartup+10;while(PlayerPrefs.GetString("is.sessionId")!=control&&Time.realtimeSinceStartup<deadline)yield return null;
                Assert.AreEqual(control,PlayerPrefs.GetString("is.sessionId"),"Must resume the same control, not create another run.");
            }finally{
                if(root!=null)UnityEngine.Object.Destroy(root);UnityEngine.Object.Destroy(settings);
                for(int i=0;i<keys.Length;i++){if(prior[i]=="")PlayerPrefs.DeleteKey(keys[i]);else PlayerPrefs.SetString(keys[i],prior[i]);}PlayerPrefs.Save();
            }
        }
        [UnityTest] public IEnumerator CanonicalBrandRequiresReturnedCandidateConfirmation()
        {
            if(Environment.GetEnvironmentVariable("IS_UNITY_CULTURAL_TESTS")!="1")
                Assert.Ignore("Requires the explicit captured-response loopback server.");
            string[] keys={"is.resumeToken","is.sessionId","is.pendingRequest","is.comparison.authored","is.comparison.cultural","is.comparison.generic_control"};
            string[] previous=Array.ConvertAll(keys,k=>PlayerPrefs.GetString(k,""));
            foreach(string key in keys) PlayerPrefs.DeleteKey(key);
            var settings=ScriptableObject.CreateInstance<ClientSettings>();
            settings.apiOrigin=Environment.GetEnvironmentVariable("IS_UNITY_TEST_API_URL") ?? "http://127.0.0.1:8043";
            GameObject root=null;
            try
            {
                root=new GameObject("Canonical brand confirmation client");
                root.AddComponent<GameClient>().settings=settings;
                yield return null;
                var ui=root.GetComponent<GameUI>();
                float deadline=Time.realtimeSinceStartup+10;
                while(!ui.CulturalAvailable && Time.realtimeSinceStartup<deadline) yield return null;
                Assert.IsTrue(ui.CulturalAvailable);
                ui.AddBrowserInterest(new Interest {name="LEGO",category="brand"});
                ui.StartCultural.Invoke();
                deadline=Time.realtimeSinceStartup+10;
                while(ui.ConfirmationCandidates.Length==0 && Time.realtimeSinceStartup<deadline) yield return null;
                int index=Array.FindIndex(ui.ConfirmationCandidates,c=>c.name=="The Lego Group" && c.category=="brand");
                Assert.GreaterOrEqual(index,0,"Canonical confirmation must come from actual returned candidates.");
                Assert.IsNull(root.GetComponent<TileWorld>().Player,"An ambiguous seed must not create a world.");
                yield return null; // Original rejected request coroutine must settle first.
                ui.ConfirmCandidate(index);
                var world=root.GetComponent<TileWorld>();
                deadline=Time.realtimeSinceStartup+10;
                while(world.Player==null && Time.realtimeSinceStartup<deadline) yield return null;
                Assert.IsNotNull(world.Player);
                GameView view=null;
                yield return root.GetComponent<ApiTransport>().Send("/v1/sessions/"+PlayerPrefs.GetString("is.sessionId"),"GET",null,v=>view=v,
                    (error,_)=>Assert.Fail(error.code));
                Assert.AreEqual("The Lego Group",view.state.cultural_context.links[0].seed.name);
                Assert.AreEqual("brand",view.state.cultural_context.links[0].seed.category);
                Assert.IsFalse(root.GetComponent<GameClient>().HasPending);
            }
            finally
            {
                if(root!=null) UnityEngine.Object.Destroy(root);
                UnityEngine.Object.Destroy(settings);
                for(int i=0;i<keys.Length;i++)
                    if(previous[i].Length==0) PlayerPrefs.DeleteKey(keys[i]); else PlayerPrefs.SetString(keys[i],previous[i]);
                PlayerPrefs.Save();
            }
        }

        [UnityTest] public IEnumerator CulturalCreationAndRestartPreserveActualCapturedIdentity()
        {
            if (Environment.GetEnvironmentVariable("IS_UNITY_CULTURAL_TESTS") != "1")
                Assert.Ignore("Requires explicit opt-in and the loopback captured-response server.");
            string[] keys={"is.resumeToken","is.sessionId","is.pendingRequest","is.comparison.authored","is.comparison.cultural","is.comparison.generic_control"};
            string[] previous=Array.ConvertAll(keys,k=>PlayerPrefs.GetString(k,""));
            foreach(string key in keys) PlayerPrefs.DeleteKey(key);
            var settings=ScriptableObject.CreateInstance<ClientSettings>();
            settings.apiOrigin=Environment.GetEnvironmentVariable("IS_UNITY_TEST_API_URL") ?? "http://127.0.0.1:8043";
            GameObject root=null;
            try
            {
                root=new GameObject("Captured response cultural client");
                root.AddComponent<GameClient>().settings=settings;
                yield return null;
                var ui=root.GetComponent<GameUI>();
                float deadline=Time.realtimeSinceStartup+10;
                while(!ui.CulturalAvailable && Time.realtimeSinceStartup<deadline) yield return null;
                Assert.IsTrue(ui.CulturalAvailable);
                Assert.IsTrue(ui.ReplayVerification,"Verification must remain visibly labelled.");
                ui.AddBrowserInterest(new Interest {name="David Bowie",category="artist"});
                ui.StartCultural.Invoke();
                var world=root.GetComponent<TileWorld>();
                deadline=Time.realtimeSinceStartup+15;
                while(world.Player==null && Time.realtimeSinceStartup<deadline) yield return null;
                Assert.IsNotNull(world.Player,"Cultural POST must create the actual world.");
                string session=PlayerPrefs.GetString("is.sessionId");
                GameView view=null;
                yield return root.GetComponent<ApiTransport>().Send("/v1/sessions/"+session,"GET",null,v=>view=v,
                    (error,_)=>Assert.Fail(error.code));
                Assert.IsNotNull(view);
                Assert.AreEqual("cultural",view.state.mode);
                Assert.AreEqual("qloo",view.state.cultural_source);
                Assert.AreEqual("David Bowie",view.state.cultural_context.links[0].seed.name);
                Assert.IsNotEmpty(view.state.cultural_context.links[0].selected_id);
                Assert.IsNotEmpty(view.state.cultural_context.links[0].recommendations);
                Assert.IsTrue(Array.Exists(view.objectives,o=>o.id.StartsWith("culture")),"Actual context adds a required quest objective.");
                UnityEngine.Object.Destroy(root);
                yield return null;
                root=new GameObject("Restarted captured response client");
                root.AddComponent<GameClient>().settings=settings;
                yield return null;
                root.GetComponent<GameUI>().Resume.Invoke();
                world=root.GetComponent<TileWorld>();
                deadline=Time.realtimeSinceStartup+10;
                while(world.Player==null && Time.realtimeSinceStartup<deadline) yield return null;
                Assert.IsNotNull(world.Player);
                Assert.AreEqual(session,PlayerPrefs.GetString("is.sessionId"));
                Assert.IsFalse(root.GetComponent<GameUI>().TitleVisible);
            }
            finally
            {
                if(root!=null) UnityEngine.Object.Destroy(root);
                UnityEngine.Object.Destroy(settings);
                for(int i=0;i<keys.Length;i++)
                    if(previous[i].Length==0) PlayerPrefs.DeleteKey(keys[i]); else PlayerPrefs.SetString(keys[i],previous[i]);
                PlayerPrefs.Save();
            }
        }
    }
}
