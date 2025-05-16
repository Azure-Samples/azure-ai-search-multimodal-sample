import React from "react";

import Editor from "@monaco-editor/react";

import {
    Body1,
    Body2,
    Button,
    Caption1,
    Dialog,
    DialogActions,
    DialogBody,
    DialogContent,
    DialogSurface,
    DialogTrigger,
    Subtitle2
} from "@fluentui/react-components";
import { ExpandUpRight20Regular } from "@fluentui/react-icons";

import { ProcessingStepType, ProcessingStepsMessage } from "../api/models";
import "./VerticalTimeline.css";

interface TimelineProps {
    processingStepMsg: Record<string, ProcessingStepsMessage[]>;
}

const VerticalTimeline: React.FC<TimelineProps> = ({ processingStepMsg }) => {
    const [editorJSON, setEditorJSON] = React.useState<string | undefined>();
    return (
        <>
            <Dialog>
                <div className="timeline-container">
                    {Object.keys(processingStepMsg).map(key => (
                        <>
                            <a>Request: {key}</a>
                            {processingStepMsg[key].map((msg, index) => (
                                <div key={index} className="timeline-item">
                                    <div className="timeline-icon">{index + 1}</div>
                                    <div className="timeline-content">
                                        <div className="timeline-section-title">
                                            <Subtitle2>{msg.processingStep.title}</Subtitle2>
                                            {msg.processingStep.type !== ProcessingStepType.Text && (
                                                <DialogTrigger disableButtonEnhancement>
                                                    <Button
                                                        appearance="subtle"
                                                        icon={<ExpandUpRight20Regular />}
                                                        onClick={() => setEditorJSON(JSON.stringify(msg.processingStep.content, null, 2))}
                                                    />
                                                </DialogTrigger>
                                            )}
                                        </div>
                                        {msg.processingStep.type === ProcessingStepType.Text ? (
                                            <Body1 block>{msg.processingStep.content}</Body1>
                                        ) : (
                                            <>
                                                <Editor
                                                    className="content-editor"
                                                    height="200px"
                                                    defaultLanguage="json"
                                                    defaultValue={JSON.stringify(msg.processingStep.content, null, 2)}
                                                    theme="vs-dark"
                                                />
                                                {Array.isArray(msg.processingStep.content) && (
                                                    <div className="image-container">
                                                        <Body2 style={{ fontWeight: "bold" }}>Images passed to LLM</Body2> <br />
                                                        <div className="image-grid">
                                                            {msg.processingStep.content
                                                                .flatMap(o => o.content)
                                                                .filter(c => c?.type === "image_url")
                                                                .map(c => (
                                                                    <img className="image-item" key={c.image_url.url} src={c.image_url.url} alt="Filtered" />
                                                                )).length > 0 ? (
                                                                msg.processingStep.content
                                                                    .flatMap(o => o.content)
                                                                    .filter(c => c?.type === "image_url")
                                                                    .map(c => (
                                                                        <img
                                                                            className="image-item"
                                                                            key={c.image_url.url}
                                                                            src={c.image_url.url}
                                                                            alt="Filtered"
                                                                        />
                                                                    ))
                                                            ) : (
                                                                <Caption1>None</Caption1>
                                                            )}
                                                        </div>
                                                    </div>
                                                )}
                                            </>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </>
                    ))}
                </div>

                <DialogSurface className="editor-dialog" mountNode={undefined}>
                    <DialogBody>
                        <DialogContent>
                            <Editor height="700px" defaultLanguage="json" defaultValue={editorJSON || ""} theme="vs-dark" />
                        </DialogContent>
                        <DialogActions>
                            <DialogTrigger disableButtonEnhancement>
                                <Button appearance="secondary">Close</Button>
                            </DialogTrigger>
                        </DialogActions>
                    </DialogBody>
                </DialogSurface>
            </Dialog>
        </>
    );
};

export default VerticalTimeline;
