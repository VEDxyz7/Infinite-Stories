using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using UnityEngine;

namespace InfiniteStories
{
    // Public display projection only. Never includes session IDs or ownership credentials.
    public static class BrowserAccessibility
    {
        [Serializable] sealed class ActionView { public string label, command; }
        [Serializable] sealed class View
        {
            public bool title, blocked, busy, pending, cultural_available;
            public string location, story, ending, panel, panel_text;
            public float x, y;
            public int revision, visits;
            public string[] objectives;
            public ActionView[] actions;
        }
#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] static extern void IS_AccessibleView(string json);
        [DllImport("__Internal")] static extern void IS_AccessibleStatus(string message);
#endif
        static string previous;
        public static void Publish(GameView game, bool title, bool blocked, bool busy, bool pending, bool culturalAvailable=false, EntityCandidate[] candidates=null,string panel="",string panelText="")
        {
            var actions=new List<ActionView>(); var objectives=new List<string>();
            if (title && candidates!=null) for (int i=0;i<candidates.Length;i++)
                actions.Add(new ActionView { label="Confirm: "+candidates[i].name+" · "+candidates[i].disambiguation,command="confirm:"+i });
            if (game!=null && !title)
            {
                foreach (var objective in game.objectives) objectives.Add((objective.completed ? "Complete: " : "Find: ")+objective.label);
                foreach (var obj in game.nearby)
                {
                    if (obj.kind=="portal") actions.Add(new ActionView { label="Travel: "+obj.name, command="travel:"+obj.id });
                    foreach (var choice in obj.choices ?? Array.Empty<StoryChoice>())
                        actions.Add(new ActionView { label=obj.name+": "+choice.label, command="choose:"+obj.id+":"+choice.id });
                }
            }
            string json=JsonUtility.ToJson(new View { panel_text=panelText,panel=panel,title=title,cultural_available=culturalAvailable,blocked=blocked,busy=busy,pending=pending,location=game?.location.name ?? "The Last Light",
                story=game?.narrative ?? "Choose the original authored chapter or resume your journey.",ending=game?.state.ending ?? "",
                x=game?.state.x ?? 0,y=game?.state.y ?? 0,revision=game?.revision ?? 0,visits=game?.state.visits ?? 0,
                objectives=objectives.ToArray(),actions=actions.ToArray() });
            if (json==previous) return; previous=json;
#if UNITY_WEBGL && !UNITY_EDITOR
            IS_AccessibleView(json);
#endif
        }
        public static void Status(string message)
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            IS_AccessibleStatus(message);
#endif
        }
    }
}
